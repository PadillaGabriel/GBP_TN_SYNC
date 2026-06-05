from decimal import Decimal

from pydantic import BaseModel


class MedidasProducto(BaseModel):
    """Medidas fisicas del producto."""

    alto: Decimal | None = None
    ancho: Decimal | None = None
    largo: Decimal | None = None
    peso: Decimal | None = None
    volumen: Decimal | None = None
