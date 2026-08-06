from pydantic import BaseModel, Field

from app.dominio.modelos.imagen import ImagenProducto
from app.dominio.modelos.precio import PrecioProducto
from app.dominio.modelos.stock import StockProducto


class VarianteProducto(BaseModel):
    """Variante normalizada de producto."""

    sku: str
    id_sistema_gbp: str | None = None
    codigo_universal: str | None = None
    codigo_alfa: str | None = None
    atributos: dict[str, str] = Field(default_factory=dict)
    stock: StockProducto | None = None
    precio_importado: PrecioProducto | None = None
    imagenes: list[ImagenProducto] = Field(default_factory=list)
