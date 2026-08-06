from pydantic import BaseModel, Field


class SyncResult(BaseModel):
    """Resultado estándar de cualquier operación de sincronización."""

    exitoso: bool
    accion: str
    sku: str | None = None
    mensaje: str
    detalles: dict[str, object] = Field(default_factory=dict)
