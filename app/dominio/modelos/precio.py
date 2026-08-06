from decimal import Decimal

from pydantic import BaseModel


class PrecioProducto(BaseModel):
    """Precio de importacion inicial."""

    monto: Decimal
    moneda: str = "ARS"
    lista_precio_id: str | None = None
    lista_precio_nombre: str | None = None
