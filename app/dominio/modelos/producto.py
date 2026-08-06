from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.dominio.modelos.imagen import ImagenProducto
from app.dominio.modelos.medidas import MedidasProducto
from app.dominio.modelos.precio import PrecioProducto
from app.dominio.modelos.stock import StockProducto


class Producto(BaseModel):
    """Producto normalizado desde GBP, independiente de SOAP/XML."""

    sku: str
    id_sistema_gbp: str
    titulo: str
    codigo_universal: str | None = None
    codigo_proveedor: str | None = None
    categoria_nombre: str | None = None
    subcategoria_nombre: str | None = None
    marca_nombre: str | None = None
    publicable_web: bool | None = None
    item_disabled: bool = False
    item_not_for_sale: bool = False
    descripcion_web: str | None = None
    medidas: MedidasProducto | None = None
    precio_importado: PrecioProducto | None = None
    stock: StockProducto | None = None
    imagenes: list[ImagenProducto] = Field(default_factory=list)
    payload_hash: str | None = None
    payload_crudo: dict[str, Any] | None = None

    @property
    def tiene_imagen_website(self) -> bool:
        """Indica si el producto tiene al menos una imagen web usable."""

        return any(imagen.url for imagen in self.imagenes)

    @property
    def tiene_descripcion_web(self) -> bool:
        """Indica si hay descripcion web real."""

        return bool((self.descripcion_web or "").strip())

    @property
    def precio_online_valido(self) -> bool:
        """Indica si existe un precio no negativo informado por GBP."""

        return (
            self.precio_importado is not None
            and self.precio_importado.monto >= Decimal("0")
        )

    @property
    def requiere_consultar_precio(self) -> bool:
        """Indica que GBP informó explícitamente precio cero."""

        return (
            self.precio_importado is not None
            and self.precio_importado.monto == Decimal("0")
        )
