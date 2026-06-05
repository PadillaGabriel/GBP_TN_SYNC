from fastapi import APIRouter

from app.settings import get_settings

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/stock/run")
async def ejecutar_sync_stock_manual() -> dict[str, object]:
    """Endpoint manual para disparar sincronizacion de stock.

    La implementacion productiva se conecta al caso de uso cuando queden
    configurados los depositos ecommerce y credenciales reales.
    """

    settings = get_settings()
    return {
        "accepted": True,
        "dry_run": settings.dry_run,
        "message": "Job de stock aceptado. Implementacion productiva pendiente de conexion.",
    }


@router.post("/audit/productos/run")
async def ejecutar_auditoria_productos_manual() -> dict[str, object]:
    """Endpoint manual para disparar auditoria GBP."""

    settings = get_settings()
    return {
        "accepted": True,
        "dry_run": settings.dry_run,
        "message": "Job de auditoria aceptado. Implementacion productiva pendiente de conexion.",
    }
