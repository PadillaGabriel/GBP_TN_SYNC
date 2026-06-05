import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.application.services.gbp_audit_service import GBPAuditService
from app.application.services.tienda_nube_import_service import TiendaNubeImportService
from app.dependencies import get_db_session
from app.settings import get_settings

router = APIRouter(prefix="/sync", tags=["sync"])
logger = logging.getLogger(__name__)


@router.post("/stock/run")
async def ejecutar_sync_stock_manual() -> dict[str, object]:
    """Endpoint manual para disparar sincronizacion de stock."""

    settings = get_settings()
    return {
        "accepted": True,
        "dry_run": settings.dry_run,
        "message": "Job de stock aceptado. Implementacion productiva pendiente de conexion.",
    }


@router.post("/audit/productos/run")
async def ejecutar_auditoria_productos_manual(
    limit: int | None = Query(default=None, ge=1, le=5000),
    concurrency: int = Query(default=3, ge=1, le=10),
    save_to_db: bool = Query(default=True),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Ejecuta auditoría real de productos GBP con precio y stock.

    No crea productos en Tienda Nube. No modifica stock en Tienda Nube.
    Persiste productos, validaciones, stock y auditoría en Railway para el panel.
    """

    settings = get_settings()
    try:
        service = GBPAuditService(settings=settings, db=db)
        return await service.ejecutar_auditoria_productos(
            limit=limit,
            concurrency=concurrency,
            guardar_en_db=save_to_db,
        )
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("AUDIT_PRODUCTS_ENDPOINT_ERROR")
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "error": f"{type(exc).__name__}: {exc}",
            "message": "La auditoría falló antes de devolver resumen. Revisar logs.",
        }


@router.post("/audit/gbp-test")
async def ejecutar_prueba_parcial_gbp(
    limit: int = Query(default=20, ge=1, le=200),
    concurrency: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Prueba parcial Render -> GBP -> parseo -> reglas -> auditoría DB.

    No crea productos en Tienda Nube. No actualiza stock. No ejecuta scheduler.
    """

    settings = get_settings()
    try:
        service = GBPAuditService(settings=settings, db=db)
        result = await service.ejecutar_prueba_parcial(
            limit=limit,
            concurrency=concurrency,
        )
        return {
            "ok": True,
            "dry_run": settings.dry_run,
            "total_catalogo": result.total_catalogo,
            "candidatos_con_imagen_website": result.candidatos_con_imagen_website,
            "procesados": result.procesados,
            "publicables_parciales": result.publicables_parciales,
            "bloqueados_parciales": result.bloqueados_parciales,
            "errores": result.errores,
            "resultados": result.resultados,
        }
    except Exception as exc:  # noqa: BLE001 - se devuelve diagnóstico al operador.
        raise HTTPException(status_code=500, detail=f"Error en prueba GBP: {exc}") from exc


@router.post("/audit/gbp-product-test")
async def ejecutar_prueba_producto_gbp(
    sku: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
    save_to_db: bool = Query(default=True),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Valida un producto completo con precio online y stock disponible.

    No crea productos en Tienda Nube. No modifica stock en Tienda Nube.
    Persiste la validación localmente para que el panel pueda mostrarla.
    """

    settings = get_settings()
    try:
        service = GBPAuditService(settings=settings, db=db)
        return await service.ejecutar_prueba_producto(
            sku=sku,
            item_id=item_id,
            guardar_en_db=save_to_db,
        )
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        raise HTTPException(status_code=500, detail=f"Error en prueba producto GBP: {exc}") from exc

@router.post("/import/tienda-nube-test")
async def importar_prueba_tienda_nube(
    limit: int = Query(default=20, ge=1, le=50),
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Importa una muestra controlada de productos publicables a Tienda Nube.

    Seguridad:
    - Con DRY_RUN=true nunca escribe en Tienda Nube.
    - Para escribir realmente se requiere DRY_RUN=false y confirm=true.
    - Solo usa productos ya validados como PUBLICABLE_AUTOMATICO.
    """

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.importar_prueba_tienda_nube(limit=limit, confirm=confirm)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_IMPORT_TEST_ENDPOINT_ERROR")
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "confirm": confirm,
            "error": f"{type(exc).__name__}: {exc}",
        }



@router.post("/import/tienda-nube-manual")
async def importar_producto_manual_tienda_nube(
    sku: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
    confirm: bool = Query(default=False),
    forzar: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Importa o actualiza manualmente un producto puntual.

    Seguridad:
    - Con DRY_RUN=true nunca escribe en Tienda Nube.
    - Para escribir realmente se requiere DRY_RUN=false y confirm=true.
    - Si el producto está bloqueado se requiere forzar=true.
    """

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.importar_producto_manual_tienda_nube(
            sku=sku,
            item_id=item_id,
            confirm=confirm,
            forzar=forzar,
        )
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_IMPORT_MANUAL_ENDPOINT_ERROR")
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "confirm": confirm,
            "forzar": forzar,
            "error": f"{type(exc).__name__}: {exc}",
        }
