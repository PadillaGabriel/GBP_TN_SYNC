import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.application.services.tienda_nube_import_service import TiendaNubeImportService
from app.dependencies import get_db_session
from app.infrastructure.persistence.repositories import (
    DepositoRepository,
    ProductoRepository,
    SyncAuditRepository,
    SyncJobRepository,
)
from app.settings import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Resumen operativo del integrador para el panel."""

    productos = ProductoRepository(db)
    auditoria = SyncAuditRepository(db)
    jobs = SyncJobRepository(db)
    settings = get_settings()
    resumen = productos.resumen_operativo_panel()
    return {
        "app_env": settings.app_env,
        "dry_run": settings.dry_run,
        "stock_scheduler_enabled": settings.stock_scheduler_enabled,
        "stock_sync_interval_minutes": settings.stock_sync_interval_minutes,
        "productos_auditados": resumen["productos_auditados"],
        "productos_mapeados_tienda_nube": resumen["productos_mapeados_tienda_nube"],
        "productos_importados": resumen["productos_mapeados_tienda_nube"],
        "publicables_total": resumen["publicables_total"],
        "publicables_pendientes_importar": resumen["publicables_pendientes_importar"],
        "bloqueados_total": resumen["bloqueados_total"],
        "bloqueados_importados_tienda_nube": resumen["bloqueados_importados_tienda_nube"],
        "bloqueados_por_motivo": resumen["bloqueados_por_motivo"],
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


@router.get("/productos/importados")
def listar_importados(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Lista productos ya mapeados en Tienda Nube."""

    productos = ProductoRepository(db)
    return {
        "limit": limit,
        "offset": offset,
        "items": productos.listar_productos_importados(limit=limit, offset=offset),
    }


@router.get("/productos/bloqueados")
def listar_bloqueados(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Lista productos bloqueados o no publicables con motivo y acción manual."""

    productos = ProductoRepository(db)
    return {
        "limit": limit,
        "offset": offset,
        "items": productos.listar_productos_bloqueados(limit=limit, offset=offset),
    }


@router.get("/decisiones/productos")
def listar_decisiones_productos(
    estado: str = Query(
        default="requiere_revision",
        description=(
            "todos, requiere_revision, bloqueado_importado, bloqueado, importado, "
            "publicable_pendiente o una decision exacta"
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Panel operativo para gestionar decisiones de importación/publicación."""

    productos = ProductoRepository(db)
    return {
        "estado": estado,
        "limit": limit,
        "offset": offset,
        "items": productos.listar_panel_decisiones(estado=estado, limit=limit, offset=offset),
    }


@router.post("/decisiones/productos/{sku}/ocultar-tn")
async def ocultar_producto_tienda_nube(
    sku: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Oculta/despublica en Tienda Nube un producto ya importado."""

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.ocultar_producto_tienda_nube(sku=sku, confirm=confirm)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_HIDE_PRODUCT_ENDPOINT_ERROR", extra={"sku": sku})
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "confirm": confirm,
            "sku": sku,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.post("/decisiones/productos/{sku}/eliminar-tn")
async def eliminar_producto_tienda_nube(
    sku: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Elimina en Tienda Nube un producto ya importado."""

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.eliminar_producto_tienda_nube(sku=sku, confirm=confirm)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_DELETE_PRODUCT_ENDPOINT_ERROR", extra={"sku": sku})
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "confirm": confirm,
            "sku": sku,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.get("/depositos")
def listar_depositos(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Lista depositos configurados para stock de Tienda Nube."""

    depositos = DepositoRepository(db)
    return {"items": depositos.listar()}
