from __future__ import annotations

from app.aplicacion.pedidos.casos_uso.cargar_pedido_temporal_gbp import (
    CargarPedidoTemporalGBP,
)
from app.aplicacion.pedidos.casos_uso.preparar_pedido_gbp import PrepararPedidoVentaGBP
from app.aplicacion.puertos.pedido_venta_gbp import PedidoVentaGBPPuerto
from app.configuracion import ConfiguracionAplicacion
from app.infraestructura.gbp.analizador_xml import parse_dataset_tables


class ConfirmacionPedidoGBPDeshabilitadaError(PermissionError):
    """La escritura final de pedidos en GBP no está habilitada."""


class PedidoGBPNoConciliadoError(RuntimeError):
    """El staging GBP no quedó conciliado y no puede confirmarse."""


class ConfirmacionPedidoGBPError(RuntimeError):
    """GBP no confirmó el pedido o no devolvió un identificador válido."""


class ConfirmacionPedidoGBPEnCursoError(RuntimeError):
    """Otra ejecución ya tomó la confirmación del pedido."""


def _extraer_soh_id(retorno: str) -> str:
    texto = str(retorno or "").strip()
    rows = parse_dataset_tables(texto)
    if rows:
        row = rows[0]
        for clave in ("soh_id", "SOH_ID", "SaleOrderID", "saleOrderId", "code", "id"):
            valor = str(row.get(clave) or "").strip()
            if valor and valor not in {"0", "-1"} and not valor.startswith("-"):
                return valor
    if texto.isdigit() and int(texto) > 0:
        return texto
    raise ConfirmacionPedidoGBPError(
        f"GBP no devolvió un soh_id positivo al confirmar: {texto!r}"
    )


class ConfirmarPedidoGBP:
    """Confirma un pedido con staging nuevo, conciliación e idempotencia fuerte."""

    def __init__(self, preparador, cliente_pedidos, repositorio, configuracion) -> None:
        self._preparador: PrepararPedidoVentaGBP = preparador
        self._cliente: PedidoVentaGBPPuerto = cliente_pedidos
        self._repo = repositorio
        self._config: ConfiguracionAplicacion = configuracion

    async def ejecutar(self, pedido_id: int) -> dict[str, object]:
        existente = self._repo.obtener_gbp_order_id(pedido_id)
        if existente:
            return {
                "ok": True,
                "codigo": "PEDIDO_GBP_YA_CONFIRMADO",
                "pedido_id": pedido_id,
                "modo": "IDEMPOTENTE",
                "pedido_confirmado": True,
                "gbp_order_id": existente,
                "guid": self._repo.obtener_gbp_guid(pedido_id),
                "escritura_ejecutada": False,
            }

        self._validar_escritura_habilitada()
        if not self._repo.iniciar_confirmacion_gbp(pedido_id):
            existente = self._repo.obtener_gbp_order_id(pedido_id)
            if existente:
                return {
                    "ok": True,
                    "codigo": "PEDIDO_GBP_YA_CONFIRMADO",
                    "pedido_id": pedido_id,
                    "modo": "IDEMPOTENTE",
                    "pedido_confirmado": True,
                    "gbp_order_id": existente,
                    "guid": self._repo.obtener_gbp_guid(pedido_id),
                    "escritura_ejecutada": False,
                }
            raise ConfirmacionPedidoGBPEnCursoError(
                f"El pedido {pedido_id} ya está siendo confirmado por otra ejecución"
            )

        try:
            plan = await self._preparador.ejecutar(pedido_id)
            staging = await CargarPedidoTemporalGBP(
                self._preparador,
                self._cliente,
                self._config,
            ).cargar_plan_preparado(pedido_id=pedido_id, plan=plan)

            conciliacion = dict(staging["conciliacion_gbp"])
            if not conciliacion.get("conciliado"):
                raise PedidoGBPNoConciliadoError(
                    "Pedido no conciliado: "
                    f"total_gbp={conciliacion.get('total_gbp')}, "
                    f"total_esperado={conciliacion.get('total_esperado')}, "
                    f"diferencia={conciliacion.get('diferencia')}"
                )

            token = await self._cliente.autenticar()
            guid = str(staging["guid"])
            await self._cliente.mantener_vivo(token, guid)
            pedido = plan["pedido"]
            observaciones = pedido.get("observaciones") or {}
            retorno = await self._cliente.confirmar_pedido(
                token,
                guid=guid,
                cliente_id=int(plan["cliente_gbp_id"]),
                tipo_documento_id=int(pedido["tipo_documento_id"]),
                condicion_venta_id=int(pedido["condicion_venta_id"]),
                transporte_id=int(pedido["transporte_id"]),
                descuento_id=int(pedido["descuento_id"]),
                observacion_1=str(observaciones.get("observacion_1") or ""),
                observacion_2=str(observaciones.get("observacion_2") or ""),
                observacion_3=str(observaciones.get("observacion_3") or ""),
                observacion_4=str(observaciones.get("observacion_4") or ""),
            )
            soh_id = _extraer_soh_id(retorno)
            self._repo.confirmar_pedido_gbp(pedido_id, soh_id, guid)

            return {
                **staging,
                "codigo": "PEDIDO_GBP_CONFIRMADO",
                "modo": "CONFIRMACION_REAL",
                "pedido_confirmado": True,
                "escritura_ejecutada": True,
                "gbp_order_id": soh_id,
                "retorno_confirmacion_gbp": retorno,
                "bloqueos": [],
                "advertencia": None,
            }
        except Exception as exc:
            self._repo.cancelar_confirmacion_gbp(pedido_id, str(exc))
            raise

    def _validar_escritura_habilitada(self) -> None:
        if self._config.dry_run:
            raise ConfirmacionPedidoGBPDeshabilitadaError(
                "DRY_RUN=true impide confirmar pedidos en GBP"
            )
        if not self._config.pedidos_escritura_gbp_habilitada:
            raise ConfirmacionPedidoGBPDeshabilitadaError(
                "La escritura GBP está deshabilitada. Active "
                "PEDIDOS_ESCRITURA_GBP_HABILITADA=true"
            )
        if not self._config.pedidos_gbp_staging_enabled:
            raise ConfirmacionPedidoGBPDeshabilitadaError(
                "La confirmación requiere PEDIDOS_GBP_STAGING_ENABLED=true"
            )
        if not self._config.pedidos_gbp_confirmation_enabled:
            raise ConfirmacionPedidoGBPDeshabilitadaError(
                "La confirmación final está deshabilitada. Active "
                "PEDIDOS_GBP_CONFIRMATION_ENABLED=true"
            )
