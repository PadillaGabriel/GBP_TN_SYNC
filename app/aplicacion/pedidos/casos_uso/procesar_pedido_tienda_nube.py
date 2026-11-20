from __future__ import annotations

from app.aplicacion.pedidos.casos_uso.confirmar_pedido_gbp import ConfirmarPedidoGBP
from app.aplicacion.pedidos.casos_uso.crear_cliente_gbp import CrearClienteGBP
from app.aplicacion.pedidos.casos_uso.importar_pedido_tienda_nube import (
    ImportarPedidoTiendaNube,
)


class ProcesarPedidoTiendaNube:
    """Orquesta el flujo completo Tiendanube -> cliente GBP -> pedido GBP.

    La idempotencia se delega en el repositorio de pedidos y en la confirmación
    de GBP, que reutiliza el ``gbp_order_id`` ya persistido cuando existe.
    """

    def __init__(
        self,
        importador: ImportarPedidoTiendaNube,
        creador_cliente: CrearClienteGBP,
        confirmador_pedido: ConfirmarPedidoGBP,
        proveedor_pedidos,
    ) -> None:
        self._importador = importador
        self._creador_cliente = creador_cliente
        self._confirmador_pedido = confirmador_pedido
        self._proveedor_pedidos = proveedor_pedidos

    async def ejecutar(self, order_id: str) -> dict[str, object]:
        actual = await self._proveedor_pedidos.get_order(order_id)
        if not isinstance(actual, dict):
            raise ValueError(f"Pedido {order_id} no encontrado en Tiendanube")
        if str(actual.get("payment_status") or "").lower() != "paid":
            raise ValueError(f"Pedido {order_id} sin pago confirmado; no se permite escribir en GBP")
        if str(actual.get("status") or "").lower() in {"cancelled", "canceled", "voided"}:
            raise ValueError(f"Pedido {order_id} cancelado o anulado; requiere revisión")
        recepcion = await self._importador.ejecutar(order_id)
        cliente = await self._creador_cliente.ejecutar(recepcion.pedido_id)
        pedido = await self._confirmador_pedido.ejecutar(recepcion.pedido_id)
        return {
            "ok": True,
            "order_id_tienda_nube": recepcion.external_order_id,
            "pedido_id": recepcion.pedido_id,
            "recepcion": recepcion.__dict__,
            "cliente_gbp": cliente,
            "pedido_gbp": pedido,
        }
