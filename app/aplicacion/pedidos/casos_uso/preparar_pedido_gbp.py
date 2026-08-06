from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto
from app.configuracion import ConfiguracionAplicacion
from app.infraestructura.gbp.cliente import ClienteGBP


class PedidoNoEncontradoParaPreparacionGBPError(LookupError):
    pass


class ClienteGBPNoVinculadoError(ValueError):
    pass


class ArticuloGBPNoResueltoError(ValueError):
    pass


class TotalesPedidoInconsistentesError(ValueError):
    pass


def _decimal(valor: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(valor if valor not in (None, "") else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _buscar_decimal(payload: dict[str, Any], *claves: str) -> Decimal | None:
    for clave in claves:
        valor = payload.get(clave)
        if valor not in (None, ""):
            try:
                return Decimal(str(valor))
            except (InvalidOperation, TypeError, ValueError):
                continue
    return None


def calcular_componentes_financieros(
    pedido: dict[str, object],
) -> dict[str, Decimal | str]:
    payload = dict(pedido.get("payload_crudo") or {})
    total = _decimal(pedido.get("total"))
    subtotal_productos = sum(
        (_decimal(item.get("unit_price")) - _decimal(item.get("discount")))
        * _decimal(item.get("quantity"))
        for item in list(pedido.get("items") or [])
    )

    envio = _buscar_decimal(
        payload,
        "shipping_cost_customer",
        "shipping_cost",
        "shipping_price",
        "shipping_amount",
    )
    descuento = _buscar_decimal(
        payload,
        "discount_coupon",
        "discount",
        "discount_amount",
        "coupon_discount",
        "promotional_discount",
    )

    fuente = "CAMPOS_TIENDA_NUBE"
    if envio is None and descuento is None:
        diferencia = total - subtotal_productos
        if diferencia >= 0:
            envio = diferencia
            descuento = Decimal("0")
            fuente = "RECONCILIACION_TOTAL_MENOS_PRODUCTOS"
        else:
            envio = Decimal("0")
            descuento = -diferencia
            fuente = "RECONCILIACION_PRODUCTOS_MENOS_TOTAL"
    else:
        envio = envio or Decimal("0")
        descuento = descuento or Decimal("0")

    calculado = subtotal_productos + envio - descuento
    return {
        "subtotal_productos": subtotal_productos,
        "envio": envio,
        "descuento": descuento,
        "total_esperado": total,
        "total_calculado": calculado,
        "diferencia": calculado - total,
        "fuente": fuente,
    }


def _observacion_gbp(valor: object, maximo: int = 250) -> str:
    texto = " ".join(str(valor or "").split())
    return texto[:maximo]


def _cargar_overrides_iva(valor: str) -> dict[str, Decimal]:
    texto = str(valor or "").strip()
    if not texto:
        return {}
    try:
        bruto = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "PEDIDOS_GBP_VAT_RATE_OVERRIDES debe ser un JSON valido"
        ) from exc
    if not isinstance(bruto, dict):
        raise ValueError("PEDIDOS_GBP_VAT_RATE_OVERRIDES debe ser un objeto JSON")
    return {str(k).strip(): _decimal(v) for k, v in bruto.items()}


def convertir_precio_final_a_neto(
    precio_final: Decimal, alicuota_iva: Decimal
) -> Decimal:
    if alicuota_iva < 0:
        raise ValueError("La alicuota de IVA no puede ser negativa")
    divisor = Decimal("1") + (alicuota_iva / Decimal("100"))
    return (precio_final / divisor).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


class PrepararPedidoVentaGBP:
    def __init__(
        self,
        repositorio: RepositorioPedidosPuerto,
        cliente_consultas: ClienteGBP,
        configuracion: ConfiguracionAplicacion,
    ) -> None:
        self._repositorio = repositorio
        self._cliente = cliente_consultas
        self._config = configuracion

    def _precio_gbp(
        self, *, sku: str, precio_final: Decimal
    ) -> tuple[Decimal, Decimal, str]:
        if not self._config.pedidos_gbp_prices_include_vat:
            return precio_final, Decimal("0"), "PRECIO_YA_NETO"
        overrides = _cargar_overrides_iva(self._config.pedidos_gbp_vat_rate_overrides)
        tasa = overrides.get(sku, self._config.pedidos_gbp_default_vat_rate)
        fuente = "OVERRIDE_SKU" if sku in overrides else "DEFAULT_CONFIG"
        return convertir_precio_final_a_neto(precio_final, tasa), tasa, fuente

    async def ejecutar(self, pedido_id: int) -> dict[str, object]:
        pedido = self._repositorio.obtener_por_id_para_validacion(pedido_id)
        if pedido is None:
            raise PedidoNoEncontradoParaPreparacionGBPError(
                f"Pedido {pedido_id} no encontrado"
            )

        cliente = dict(pedido.get("cliente") or {})
        cust_id = cliente.get("gbp_customer_id")
        if not cust_id:
            raise ClienteGBPNoVinculadoError(
                "El pedido no tiene un cliente GBP vinculado"
            )

        token = await self._cliente.autenticar()
        items_plan: list[dict[str, object]] = []
        for item in list(pedido.get("items") or []):
            sku = str(item.get("sku") or "").strip()
            item_id = await self._cliente.obtener_item_id_por_codigo(token, sku)
            if not item_id:
                raise ArticuloGBPNoResueltoError(
                    f"No se pudo resolver item_id GBP para SKU {sku}"
                )
            cantidad = _decimal(item.get("quantity"))
            precio_bruto = _decimal(item.get("unit_price")) - _decimal(
                item.get("discount")
            )
            precio_gbp, iva, fuente_iva = self._precio_gbp(
                sku=sku, precio_final=precio_bruto
            )
            items_plan.append(
                {
                    "tipo": "PRODUCTO",
                    "sku": sku,
                    "item_id": int(item_id),
                    "deposito_id": self._config.pedidos_gbp_storage_id,
                    "lista_precio_id": self._config.pedidos_gbp_price_list_id,
                    "cantidad": str(cantidad),
                    "precio_final_tn": str(precio_bruto),
                    "precio_neto_gbp": str(precio_gbp),
                    "precio_final": str(precio_gbp),
                    "iva_porcentaje": str(iva),
                    "iva_fuente": fuente_iva,
                    "moneda_id": self._config.pedidos_gbp_currency_id,
                }
            )

        finanzas = calcular_componentes_financieros(pedido)
        diferencia = abs(finanzas["diferencia"])
        if diferencia > self._config.pedidos_gbp_total_tolerance:
            raise TotalesPedidoInconsistentesError(
                f"Los componentes del pedido difieren del total Tienda Nube en {diferencia}"
            )

        envio = finanzas["envio"]
        if envio > 0:
            cantidad_envio = Decimal(str(self._config.pedidos_gbp_shipping_special_qty))
            if cantidad_envio == 0:
                raise TotalesPedidoInconsistentesError(
                    "PEDIDOS_GBP_SHIPPING_SPECIAL_QTY no puede ser 0"
                )
            # Item_funInsertData_withPrice calcula cantidad por precio unitario.
            # El importe total de la línea debe conservar exactamente el envío TN.
            # Con cantidad 1 el precio queda positivo; con una cantidad especial
            # negativa el precio queda negativo, manteniendo siempre un total positivo.
            precio_final_unitario_envio = envio / cantidad_envio
            precio_gbp, iva, fuente_iva = self._precio_gbp(
                sku="ENVIO", precio_final=precio_final_unitario_envio
            )
            items_plan.append(
                {
                    "tipo": "ENVIO",
                    "sku": "ENVIO",
                    "item_id": self._config.pedidos_gbp_shipping_item_id,
                    "deposito_id": self._config.pedidos_gbp_storage_id,
                    "lista_precio_id": self._config.pedidos_gbp_price_list_id,
                    "cantidad": str(cantidad_envio),
                    "precio_final_tn": str(envio),
                    "precio_final_unitario_gbp_con_iva": str(
                        precio_final_unitario_envio
                    ),
                    "precio_neto_gbp": str(precio_gbp),
                    "precio_final": str(precio_gbp),
                    "iva_porcentaje": str(iva),
                    "iva_fuente": fuente_iva,
                    "moneda_id": self._config.pedidos_gbp_currency_id,
                }
            )

        descuento = finanzas["descuento"]
        if descuento > 0:
            discount_item_id = await self._cliente.obtener_item_id_por_codigo(
                token, self._config.pedidos_gbp_discount_item_code
            )
            if not discount_item_id:
                raise ArticuloGBPNoResueltoError(
                    f"No se pudo resolver item_id GBP para descuento {self._config.pedidos_gbp_discount_item_code}"
                )
            precio_gbp, iva, fuente_iva = self._precio_gbp(
                sku=self._config.pedidos_gbp_discount_item_code,
                precio_final=descuento,
            )
            items_plan.append(
                {
                    "tipo": "DESCUENTO",
                    "sku": self._config.pedidos_gbp_discount_item_code,
                    "item_id": int(discount_item_id),
                    "deposito_id": self._config.pedidos_gbp_storage_id,
                    "lista_precio_id": self._config.pedidos_gbp_price_list_id,
                    "cantidad": str(self._config.pedidos_gbp_discount_special_qty),
                    "precio_final_tn": str(descuento),
                    "precio_neto_gbp": str(precio_gbp),
                    "precio_final": str(precio_gbp),
                    "iva_porcentaje": str(iva),
                    "iva_fuente": fuente_iva,
                    "moneda_id": self._config.pedidos_gbp_currency_id,
                }
            )

        observaciones = {
            "observacion_1": _observacion_gbp("ORIGEN: TIENDANUBE"),
            "observacion_2": _observacion_gbp(
                f"TN_ORDER_ID: {pedido.get('external_order_id') or ''}"
            ),
            "observacion_3": _observacion_gbp(
                f"TN_ORDER_NUMBER: {pedido.get('numero_pedido') or ''}"
            ),
            "observacion_4": _observacion_gbp("INTEGRADOR: GBP_TN_SYNC"),
        }

        return {
            "ok": True,
            "codigo": "PEDIDO_GBP_PREPARADO",
            "pedido_id": pedido_id,
            "modo": "SIMULACION",
            "escritura_ejecutada": False,
            "requiere_confirmacion": True,
            "cliente_gbp_id": int(cust_id),
            "flujo_oficial": [
                "Identifier_funGetData",
                "Item_funInsertData_withPrice",
                "SaleOrder_updateIsEditing",
                "SaleOrder_fungetDataByGuid",
                "SaleOrder_funGetTotals",
                "SaleOrder_funInsertDataV3",
            ],
            "tratamiento_precios": {
                "entrada_tienda_nube": "PRECIO_FINAL_CON_IVA"
                if self._config.pedidos_gbp_prices_include_vat
                else "PRECIO_NETO",
                "salida_ws_sale_order": "PRECIO_NETO",
                "iva_default": str(self._config.pedidos_gbp_default_vat_rate),
                "overrides_configurados": bool(
                    str(self._config.pedidos_gbp_vat_rate_overrides or "").strip()
                ),
            },
            "totales": {
                k: str(v) if isinstance(v, Decimal) else v for k, v in finanzas.items()
            },
            "pedido": {
                "sucursal_id": self._config.pedidos_gbp_branch_id,
                "condicion_venta_id": self._config.pedidos_gbp_sales_terms_id,
                "tipo_documento_id": self._config.pedidos_gbp_order_type_id,
                "transporte_id": self._config.pedidos_gbp_delivery_id,
                "descuento_id": self._config.pedidos_gbp_discount_id,
                "observaciones": observaciones,
                "items": items_plan,
            },
            "bloqueos": [
                "GENERACION_GUID_NO_EJECUTADA_EN_SIMULACION",
                "ITEMS_NO_INSERTADOS",
                "PEDIDO_NO_CONFIRMADO",
            ],
        }
