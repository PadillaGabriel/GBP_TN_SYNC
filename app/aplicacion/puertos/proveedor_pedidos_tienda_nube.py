from typing import Any, Protocol


class ProveedorPedidosTiendaNube(Protocol):
    async def get_order(self, order_id: str) -> dict[str, Any] | None: ...
