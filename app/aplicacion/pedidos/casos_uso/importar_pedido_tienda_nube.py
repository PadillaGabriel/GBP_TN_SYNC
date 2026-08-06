from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from app.aplicacion.pedidos.casos_uso.recibir_pedido import RecibirPedido
from app.aplicacion.pedidos.modelos import ResultadoRecepcionPedido
from app.aplicacion.puertos.proveedor_pedidos_tienda_nube import (
    ProveedorPedidosTiendaNube,
)
from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto
from app.dominio.pedidos import (
    ClientePedidoExterno,
    DireccionEnvioPedido,
    ItemPedidoExterno,
    PedidoExterno,
)


class PedidoTiendaNubeNoEncontradoError(LookupError):
    pass


class PedidoTiendaNubeInvalidoError(ValueError):
    pass


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    resultado = str(valor).strip()
    return resultado or None


def _decimal(valor: object, *, campo: str) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PedidoTiendaNubeInvalidoError(
            f"El campo {campo} no contiene un decimal válido"
        ) from exc


def _entero_positivo(valor: object, *, campo: str) -> int:
    try:
        resultado = int(str(valor))
    except (TypeError, ValueError) as exc:
        raise PedidoTiendaNubeInvalidoError(
            f"El campo {campo} no contiene un entero válido"
        ) from exc
    if resultado <= 0:
        raise PedidoTiendaNubeInvalidoError(f"El campo {campo} debe ser mayor que cero")
    return resultado


def _fecha(valor: object) -> datetime:
    texto = _texto(valor)
    if not texto:
        raise PedidoTiendaNubeInvalidoError("El pedido no informa created_at")
    normalizado = texto.replace("Z", "+00:00")
    if (
        len(normalizado) >= 5
        and normalizado[-5] in {"+", "-"}
        and normalizado[-3] != ":"
    ):
        normalizado = f"{normalizado[:-2]}:{normalizado[-2:]}"
    try:
        return datetime.fromisoformat(normalizado)
    except ValueError as exc:
        raise PedidoTiendaNubeInvalidoError(
            "created_at tiene un formato inválido"
        ) from exc


def _separar_nombre(nombre_completo: object) -> tuple[str, str]:
    texto = _texto(nombre_completo) or "Cliente Tienda Nube"
    partes = texto.split()
    if len(partes) == 1:
        return partes[0], "-"
    return partes[0], " ".join(partes[1:])


def _sanitizar_payload(valor: Any) -> Any:
    """Elimina secretos antes de persistir el payload crudo."""
    claves_sensibles = {"token", "access_token", "authorization", "authentication"}
    if isinstance(valor, dict):
        return {
            str(clave): _sanitizar_payload(contenido)
            for clave, contenido in valor.items()
            if str(clave).lower() not in claves_sensibles
        }
    if isinstance(valor, list):
        return [_sanitizar_payload(elemento) for elemento in valor]
    return valor


class ImportarPedidoTiendaNube:
    """Obtiene una orden de Tienda Nube y la persiste de forma idempotente."""

    def __init__(
        self,
        proveedor: ProveedorPedidosTiendaNube,
        repositorio: RepositorioPedidosPuerto,
    ) -> None:
        self._proveedor = proveedor
        self._repositorio = repositorio

    async def ejecutar(self, order_id: str) -> ResultadoRecepcionPedido:
        order_id_normalizado = str(order_id).strip()
        if not order_id_normalizado:
            raise PedidoTiendaNubeInvalidoError("El order_id es obligatorio")

        payload = await self._proveedor.get_order(order_id_normalizado)
        if payload is None:
            raise PedidoTiendaNubeNoEncontradoError(
                f"Pedido Tienda Nube {order_id_normalizado} no encontrado"
            )

        pedido = self._mapear(payload)
        request_id = str(uuid4())
        return RecibirPedido(self._repositorio).ejecutar(pedido, request_id, request_id)

    @staticmethod
    def _mapear(payload: dict[str, Any]) -> PedidoExterno:
        customer = (
            payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
        )
        shipping = (
            payload.get("shipping_address")
            if isinstance(payload.get("shipping_address"), dict)
            else {}
        )
        products = payload.get("products")
        if not isinstance(products, list) or not products:
            raise PedidoTiendaNubeInvalidoError("El pedido no contiene productos")

        nombre, apellido = _separar_nombre(
            customer.get("name")
            or payload.get("contact_name")
            or payload.get("billing_name")
        )

        cliente = ClientePedidoExterno(
            external_customer_id=_texto(customer.get("id")),
            nombre=nombre,
            apellido=apellido,
            email=_texto(customer.get("email") or payload.get("contact_email")),
            telefono=_texto(customer.get("phone") or payload.get("contact_phone")),
            tipo_documento=_texto(
                customer.get("document_type") or payload.get("billing_document_type")
            ),
            numero_documento=_texto(
                customer.get("identification") or payload.get("contact_identification")
            ),
        )

        envio = None
        if shipping:
            calle = _texto(shipping.get("address")) or ""
            numero = _texto(shipping.get("number")) or ""
            direccion = " ".join(parte for parte in (calle, numero) if parte).strip()
            envio = DireccionEnvioPedido(
                destinatario=_texto(shipping.get("name"))
                or f"{nombre} {apellido}".strip(),
                direccion=direccion or "Sin dirección",
                ciudad=_texto(shipping.get("city")) or "Sin ciudad",
                provincia=_texto(shipping.get("province")) or "Sin provincia",
                codigo_postal=_texto(shipping.get("zipcode")) or "",
                pais=_texto(shipping.get("country")) or "AR",
            )

        items: list[ItemPedidoExterno] = []
        for indice, product in enumerate(products, start=1):
            if not isinstance(product, dict):
                raise PedidoTiendaNubeInvalidoError(
                    f"El producto {indice} tiene formato inválido"
                )
            sku = _texto(product.get("sku"))
            if not sku:
                raise PedidoTiendaNubeInvalidoError(
                    f"El producto {indice} no informa SKU"
                )
            items.append(
                ItemPedidoExterno(
                    external_item_id=_texto(product.get("id")) or f"ITEM-{indice}",
                    external_variant_id=_texto(product.get("variant_id")),
                    sku=sku,
                    cantidad=_entero_positivo(
                        product.get("quantity"), campo=f"products[{indice}].quantity"
                    ),
                    precio_unitario=_decimal(
                        product.get("price"), campo=f"products[{indice}].price"
                    ),
                    descuento=Decimal("0"),
                    titulo=_texto(product.get("name")),
                )
            )

        external_order_id = _texto(payload.get("id"))
        if not external_order_id:
            raise PedidoTiendaNubeInvalidoError("El pedido no informa id")

        return PedidoExterno(
            canal="TIENDA_NUBE",
            external_order_id=external_order_id,
            numero_pedido=_texto(payload.get("number")),
            moneda=(_texto(payload.get("currency")) or "ARS").upper(),
            total=_decimal(payload.get("total"), campo="total"),
            creado_en=_fecha(payload.get("created_at")),
            cliente=cliente,
            envio=envio,
            items=tuple(items),
            payload_crudo=_sanitizar_payload(payload),
        )
