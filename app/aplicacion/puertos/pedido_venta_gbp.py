from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class PedidoVentaGBPPuerto(Protocol):
    async def probar_conexion(self) -> dict[str, object]: ...

    async def autenticar(self) -> str: ...

    async def obtener_identificador(self, token: str) -> str: ...

    async def insertar_item(
        self,
        token: str,
        *,
        guid: str,
        deposito_id: int,
        item_id: int,
        lista_precio_id: int,
        cantidad: Decimal,
        precio: Decimal,
        moneda_id: int,
    ) -> str: ...

    async def mantener_vivo(self, token: str, guid: str) -> str: ...

    async def obtener_datos_por_guid(self, token: str, guid: str) -> str: ...

    async def confirmar_pedido(
        self,
        token: str,
        *,
        guid: str,
        cliente_id: int,
        tipo_documento_id: int,
        condicion_venta_id: int,
        transporte_id: int,
        descuento_id: int,
        observacion_1: str,
        observacion_2: str,
        observacion_3: str,
        observacion_4: str,
    ) -> str: ...

    async def obtener_totales(
        self,
        token: str,
        *,
        guid: str,
        cliente_id: int,
        tipo_documento_id: int,
    ) -> str: ...
