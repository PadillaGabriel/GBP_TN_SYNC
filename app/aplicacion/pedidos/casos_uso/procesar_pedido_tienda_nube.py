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
    ) -> None:
        self._importador = importador
        self._creador_cliente = creador_cliente
        self._confirmador_pedido = confirmador_pedido

    async def ejecutar(self, order_id: str) -> dict[str, object]:
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
