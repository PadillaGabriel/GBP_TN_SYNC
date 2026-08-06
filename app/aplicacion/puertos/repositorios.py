"""Contratos de persistencia utilizados por los casos de uso.

Estos protocolos evitan que la capa de aplicación dependa de SQLAlchemy o de
implementaciones concretas de infraestructura.
"""

from typing import Protocol

from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockProducto


class RepositorioProductosPuerto(Protocol):
    """Operaciones mínimas requeridas sobre productos y stock."""

    def obtener_stock(self, sku: str) -> int | None: ...

    def guardar_stock(self, stock: StockProducto) -> object: ...

    def guardar_producto(self, producto: Producto) -> object: ...


class RepositorioAuditoriaPuerto(Protocol):
    """Registro de resultados operacionales de sincronización."""

    def registrar(
        self,
        *,
        sku: str | None,
        accion: str,
        estado: str,
        mensaje: str,
        metodo_gbp: str | None = None,
        duracion_ms: int | None = None,
    ) -> None: ...
