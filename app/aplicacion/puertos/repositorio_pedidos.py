from typing import Protocol

from app.aplicacion.pedidos.modelos import ResultadoRecepcionPedido
from app.dominio.pedidos import PedidoExterno


class RepositorioPedidosPuerto(Protocol):
    def recibir_idempotente(
        self, pedido: PedidoExterno, request_id: str, correlation_id: str
    ) -> ResultadoRecepcionPedido: ...
    def obtener_por_clave(
        self, canal: str, external_order_id: str
    ) -> dict[str, object] | None: ...
    def obtener_por_id_para_validacion(
        self, pedido_id: int
    ) -> dict[str, object] | None: ...
    def vincular_cliente_gbp(self, pedido_id: int, cust_id: int) -> None: ...
