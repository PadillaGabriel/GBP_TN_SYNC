from app.aplicacion.pedidos.modelos import ResultadoRecepcionPedido
from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto
from app.dominio.pedidos import PedidoExterno


class RecibirPedido:
    def __init__(self, repositorio: RepositorioPedidosPuerto) -> None:
        self._repositorio = repositorio

    def ejecutar(
        self, pedido: PedidoExterno, request_id: str, correlation_id: str
    ) -> ResultadoRecepcionPedido:
        if not pedido.items:
            raise ValueError("El pedido debe contener al menos un ítem")
        if any(item.cantidad <= 0 for item in pedido.items):
            raise ValueError("Todas las cantidades deben ser mayores que cero")
        if any(not item.sku.strip() for item in pedido.items):
            raise ValueError("Todos los ítems deben tener SKU")
        return self._repositorio.recibir_idempotente(pedido, request_id, correlation_id)
