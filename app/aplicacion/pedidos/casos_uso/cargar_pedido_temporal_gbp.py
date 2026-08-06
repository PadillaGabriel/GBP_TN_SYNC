from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.aplicacion.pedidos.casos_uso.analizar_detalle_temporal_gbp import (
    analizar_expansion_temporal_gbp,
)
from app.aplicacion.pedidos.casos_uso.preparar_pedido_gbp import (
    PrepararPedidoVentaGBP,
    convertir_precio_final_a_neto,
)
from app.aplicacion.puertos.pedido_venta_gbp import PedidoVentaGBPPuerto
from app.configuracion import ConfiguracionAplicacion
from app.infraestructura.gbp.analizador_xml import parse_dataset_tables


class CargaTemporalGBPDeshabilitadaError(PermissionError):
    pass


class InsercionItemTemporalGBPError(RuntimeError):
    pass


def _decimal_seguro(valor: object) -> Decimal | None:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def analizar_totales_gbp(
    xml: str, total_esperado: Decimal, tolerancia: Decimal
) -> dict[str, object]:
    rows = parse_dataset_tables(xml)
    row = rows[0] if rows else {}
    total_gbp = _decimal_seguro(row.get("Total"))
    total_neto = _decimal_seguro(row.get("TotalNeto"))
    impuestos = _decimal_seguro(row.get("TotalTaxes"))
    descuento = _decimal_seguro(row.get("TotalDiscount"))
    error_code = str(row.get("ErrorCode") or "").strip()
    diferencia = (total_gbp - total_esperado) if total_gbp is not None else None
    conciliado = (
        error_code in ("", "0")
        and diferencia is not None
        and abs(diferencia) <= tolerancia
    )
    return {
        "error_code": error_code,
        "total_gbp": str(total_gbp) if total_gbp is not None else None,
        "total_esperado": str(total_esperado),
        "diferencia": str(diferencia) if diferencia is not None else None,
        "total_neto_gbp": str(total_neto) if total_neto is not None else None,
        "impuestos_gbp": str(impuestos) if impuestos is not None else None,
        "descuento_gbp": str(descuento) if descuento is not None else None,
        "tolerancia": str(tolerancia),
        "conciliado": conciliado,
    }


class CargarPedidoTemporalGBP:
    """Carga un pedido en el buffer transaccional de GBP sin confirmarlo."""

    def __init__(
        self,
        preparador: PrepararPedidoVentaGBP,
        cliente_pedidos: PedidoVentaGBPPuerto,
        configuracion: ConfiguracionAplicacion,
    ) -> None:
        self._preparador = preparador
        self._cliente = cliente_pedidos
        self._config = configuracion

    async def _cargar_plan(
        self,
        *,
        token: str,
        items: list[dict[str, object]],
    ) -> tuple[str, list[dict[str, object]], str]:
        guid = await self._cliente.obtener_identificador(token)
        resultados: list[dict[str, object]] = []

        for indice, item in enumerate(items, start=1):
            if indice > 1:
                await self._cliente.mantener_vivo(token, guid)
            retorno = (
                await self._cliente.insertar_item(
                    token,
                    guid=guid,
                    deposito_id=int(item["deposito_id"]),
                    item_id=int(item["item_id"]),
                    lista_precio_id=int(item["lista_precio_id"]),
                    cantidad=Decimal(str(item["cantidad"])),
                    precio=Decimal(str(item["precio_neto_gbp"])),
                    moneda_id=int(item["moneda_id"]),
                )
            ).strip()
            if not retorno or retorno.startswith("-") or retorno == "0":
                raise InsercionItemTemporalGBPError(
                    f"GBP rechazo item temporal {item['sku']} ({item['tipo']}): "
                    f"retorno={retorno!r}, guid={guid}"
                )
            resultados.append(
                {
                    "orden": indice,
                    "tipo": item["tipo"],
                    "sku": item["sku"],
                    "item_id": item["item_id"],
                    "cantidad": item["cantidad"],
                    "precio_final_tn": item["precio_final_tn"],
                    "precio_neto_enviado_gbp": item["precio_neto_gbp"],
                    "iva_porcentaje": item["iva_porcentaje"],
                    "iva_fuente": item["iva_fuente"],
                    "retorno": retorno,
                }
            )

        await self._cliente.mantener_vivo(token, guid)
        detalle = await self._cliente.obtener_datos_por_guid(token, guid)
        return guid, resultados, detalle

    def _ajustar_descuento_por_residuo(
        self,
        items: list[dict[str, object]],
        diferencia: Decimal,
    ) -> tuple[list[dict[str, object]], dict[str, str]] | None:
        if abs(diferencia) > self._config.pedidos_gbp_residual_maximo_ajustable:
            return None

        indice_descuento = next(
            (i for i, item in enumerate(items) if item.get("tipo") == "DESCUENTO"),
            None,
        )
        if indice_descuento is None:
            return None

        originales = [dict(item) for item in items]
        descuento = originales[indice_descuento]
        importe_original = Decimal(str(descuento["precio_final_tn"]))
        importe_ajustado = (importe_original + diferencia).quantize(Decimal("0.01"))
        if importe_ajustado <= 0:
            return None

        iva = Decimal(str(descuento["iva_porcentaje"]))
        neto_ajustado = convertir_precio_final_a_neto(importe_ajustado, iva)
        descuento["precio_final_tn"] = str(importe_ajustado)
        descuento["precio_neto_gbp"] = str(neto_ajustado)
        descuento["precio_final"] = str(neto_ajustado)

        return originales, {
            "tipo": "AJUSTE_RESIDUAL_SOBRE_CUPON",
            "diferencia_inicial": str(diferencia),
            "descuento_original": str(importe_original),
            "descuento_ajustado": str(importe_ajustado),
            "neto_ajustado": str(neto_ajustado),
        }

    async def ejecutar(self, pedido_id: int) -> dict[str, object]:
        plan = await self._preparador.ejecutar(pedido_id)
        return await self.cargar_plan_preparado(pedido_id=pedido_id, plan=plan)

    async def cargar_plan_preparado(
        self,
        *,
        pedido_id: int,
        plan: dict[str, object],
    ) -> dict[str, object]:
        """Materializa un plan preparado en un staging GBP nuevo y conciliado.

        Siempre genera un GUID nuevo. Esta regla evita reutilizar buffers vencidos y
        permite que la confirmación final se apoye en exactamente el mismo flujo
        validado por el endpoint de staging.
        """
        if not self._config.pedidos_gbp_staging_enabled:
            raise CargaTemporalGBPDeshabilitadaError(
                "La carga temporal GBP esta deshabilitada. "
                "Active PEDIDOS_GBP_STAGING_ENABLED=true"
            )
        if self._config.dry_run:
            raise CargaTemporalGBPDeshabilitadaError(
                "DRY_RUN=true impide generar GUID e insertar items temporales en GBP"
            )

        token = await self._cliente.autenticar()
        items = [dict(item) for item in plan["pedido"]["items"]]
        guid, resultados, detalle = await self._cargar_plan(token=token, items=items)
        totales = await self._cliente.obtener_totales(
            token,
            guid=guid,
            cliente_id=int(plan["cliente_gbp_id"]),
            tipo_documento_id=int(plan["pedido"]["tipo_documento_id"]),
        )
        total_esperado = Decimal(str(plan["totales"]["total_esperado"]))
        conciliacion = analizar_totales_gbp(
            totales, total_esperado, self._config.pedidos_gbp_total_tolerance
        )

        ajuste_residual: dict[str, str] | None = None
        guid_inicial: str | None = None
        conciliacion_inicial: dict[str, object] | None = None
        diferencia = _decimal_seguro(conciliacion.get("diferencia"))
        if not conciliacion["conciliado"] and diferencia is not None:
            ajuste = self._ajustar_descuento_por_residuo(items, diferencia)
            if ajuste is not None:
                items_ajustados, ajuste_residual = ajuste
                guid_inicial = guid
                conciliacion_inicial = conciliacion
                guid, resultados, detalle = await self._cargar_plan(
                    token=token, items=items_ajustados
                )
                totales = await self._cliente.obtener_totales(
                    token,
                    guid=guid,
                    cliente_id=int(plan["cliente_gbp_id"]),
                    tipo_documento_id=int(plan["pedido"]["tipo_documento_id"]),
                )
                conciliacion = analizar_totales_gbp(
                    totales, total_esperado, self._config.pedidos_gbp_total_tolerance
                )

        expansion = analizar_expansion_temporal_gbp(detalle, resultados)
        bloqueos = ["PEDIDO_FINAL_NO_CONFIRMADO"]
        if not conciliacion["conciliado"]:
            bloqueos.append("TOTAL_GBP_NO_CONCILIADO")

        return {
            "ok": True,
            "codigo": "PEDIDO_GBP_TEMPORAL_CARGADO",
            "pedido_id": pedido_id,
            "modo": "STAGING_SIN_CONFIRMACION",
            "escritura_temporal_ejecutada": True,
            "pedido_confirmado": False,
            "guid": guid,
            "guid_inicial_descartado": guid_inicial,
            "items_insertados": resultados,
            "detalle_gbp_xml": detalle,
            "expansion_gbp": expansion,
            "totales_gbp_xml": totales,
            "totales_esperados": plan["totales"],
            "conciliacion_gbp_inicial": conciliacion_inicial,
            "ajuste_residual": ajuste_residual,
            "conciliacion_gbp": conciliacion,
            "apto_para_confirmacion_futura": bool(conciliacion["conciliado"]),
            "bloqueos": bloqueos,
            "advertencia": (
                "El buffer temporal puede expirar y ser eliminado automaticamente por GBP."
            ),
        }
