from pydantic import BaseModel


class ImagenProducto(BaseModel):
    """Imagen web normalizada de GBP."""

    url: str
    orden: int = 1
    origen: str = "gbp_website"
