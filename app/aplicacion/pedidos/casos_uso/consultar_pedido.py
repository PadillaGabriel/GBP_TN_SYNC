from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto


class ConsultarPedido:
    def __init__(self, repositorio: RepositorioPedidosPuerto) -> None:
        self._repositorio = repositorio

    def ejecutar(self, canal: str, external_order_id: str) -> dict[str, object] | None:
        return self._repositorio.obtener_por_clave(
            canal.strip().upper(), external_order_id.strip()
        )
