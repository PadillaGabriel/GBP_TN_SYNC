from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db_session
from app.infrastructure.persistence.repositories import (
    DepositoRepository,
    ProductoRepository,
    SyncAuditRepository,
    SyncJobRepository,
)
from app.settings import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Resumen operativo del integrador para el panel."""

    productos = ProductoRepository(db)
    auditoria = SyncAuditRepository(db)
    jobs = SyncJobRepository(db)
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "dry_run": settings.dry_run,
        "stock_scheduler_enabled": settings.stock_scheduler_enabled,
        "stock_sync_interval_minutes": settings.stock_sync_interval_minutes,
        "productos_importados": productos.contar_productos(),
        "decisiones": productos.contar_por_decision(),
        "jobs": jobs.contar_por_estado(),
        "ultimo_evento": auditoria.obtener_ultimo_evento(),
    }


@router.get("/productos")
def listar_productos(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Lista productos con matriz de validacion visible."""

    productos = ProductoRepository(db)
    return {
        "limit": limit,
        "offset": offset,
        "items": productos.listar_panel_productos(limit=limit, offset=offset),
    }


@router.get("/productos/bloqueados")
def listar_bloqueados(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Lista productos bloqueados o no publicables."""

    productos = ProductoRepository(db)
    items = [
        item
        for item in productos.listar_panel_productos(limit=500)
        if str(item.get("decision", "")).startswith("NO_PUBLICAR")
    ]
    return {"items": items}


@router.get("/depositos")
def listar_depositos(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Lista depositos configurados para stock de Tienda Nube."""

    depositos = DepositoRepository(db)
    return {"items": depositos.listar()}
