from __future__ import annotations

from typing import Any

from app.aplicacion.puertos.repositorios import RepositorioProductosPuerto
from app.dominio.modelos.producto import Producto


class PersistidorProductoValidado:
    """Persiste producto, validación y stock como una única responsabilidad."""

    def __init__(self, repositorio_productos: RepositorioProductosPuerto) -> None:
        self._repositorio = repositorio_productos

    def guardar(self, producto: Producto, validacion: Any) -> None:
        modelo = self._repositorio.guardar_producto(producto)
        self._repositorio.guardar_validacion(modelo.id, producto, validacion)
        if producto.stock is not None:
            self._repositorio.guardar_stock(modelo.id, producto.stock)
