import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.application.jobs.bulk_jobs import ejecutar_job_auditar_todo, ejecutar_job_importar_todo
from app.application.services.gbp_audit_service import GBPAuditService
from app.application.services.tienda_nube_import_service import TiendaNubeImportService
from app.dependencies import get_db_session
from app.infrastructure.persistence.repositories import SyncJobRepository
from app.settings import get_settings

router = APIRouter(prefix="/sync", tags=["sync"])
logger = logging.getLogger(__name__)


@router.post("/jobs/audit-all")
async def iniciar_job_auditar_todo(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Inicia auditoría total de candidatos GBP pendientes en segundo plano."""

    job = SyncJobRepository(db).crear(
        tipo="AUDITAR_TODO_GBP",
        progreso={
            "mensaje": "Job creado. Esperando inicio de auditoría total.",
            "batch_limit": batch_limit,
            "concurrency": concurrency,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_auditar_todo,
        job_id=job.id,
        batch_limit=batch_limit,
        concurrency=concurrency,
    )
    return {
        "ok": True,
        "job_id": job.id,
        "tipo": job.tipo,
        "estado": job.estado,
        "status_url": f"/sync/jobs/{job.id}",
    }


@router.post("/jobs/import-all")
async def iniciar_job_importar_todo(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Inicia importación total de publicables pendientes en segundo plano."""

    settings = get_settings()
    job = SyncJobRepository(db).crear(
        tipo="IMPORTAR_TODO_TN",
        progreso={
            "mensaje": "Job creado. Esperando inicio de importación total.",
            "batch_limit": batch_limit,
            "dry_run": settings.dry_run,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_importar_todo,
        job_id=job.id,
        batch_limit=batch_limit,
    )
    return {
        "ok": True,
        "job_id": job.id,
        "tipo": job.tipo,
        "estado": job.estado,
        "dry_run": settings.dry_run,
        "status_url": f"/sync/jobs/{job.id}",
    }


@router.get("/jobs/{job_id}")
def obtener_job(job_id: int, db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Consulta estado y progreso de un job largo."""

    data = SyncJobRepository(db).obtener_serializado(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {"ok": True, "job": data}


@router.post("/import/tienda-nube-sku")
async def importar_sku_directo_tienda_nube(
    sku: str = Query(..., min_length=1),
    confirm: bool = Query(default=True),
    forzar: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Busca un SKU en GBP, lo valida, lo persiste y lo importa/actualiza en Tienda Nube."""

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.importar_producto_manual_tienda_nube(
            sku=sku,
            confirm=confirm,
            forzar=forzar,
        )
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_IMPORT_SKU_DIRECT_ENDPOINT_ERROR", extra={"sku": sku})
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "confirm": confirm,
            "forzar": forzar,
            "sku": sku,
            "error": f"{type(exc).__name__}: {exc}",
        }


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




@router.post("/audit/productos/next")
async def ejecutar_auditoria_productos_siguientes(
    limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    save_to_db: bool = Query(default=True),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Audita los próximos productos con imagen Website que todavía no fueron auditados.

    Evita reprocesar siempre desde el inicio del catálogo y permite avanzar por tandas.
    No crea productos en Tienda Nube.
    """

    settings = get_settings()
    try:
        service = GBPAuditService(settings=settings, db=db)
        return await service.ejecutar_auditoria_productos(
            limit=limit,
            concurrency=concurrency,
            guardar_en_db=save_to_db,
            solo_no_auditados=True,
        )
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("AUDIT_PRODUCTS_NEXT_ENDPOINT_ERROR")
        return {
            "ok": False,
            "dry_run": settings.dry_run,
            "error": f"{type(exc).__name__}: {exc}",
            "message": "La auditoría incremental falló antes de devolver resumen. Revisar logs.",
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



@router.post("/audit/gbp-product-description-debug")
async def diagnosticar_descripcion_producto_gbp(
    sku: str | None = Query(default=None),
    item_id: int | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Diagnostica qué campos descriptivos devuelve GBP para un producto.

    No crea productos en Tienda Nube. No modifica Tienda Nube.
    Sirve para validar si WebSite_Description viene corto y si existe otro
    campo web descriptivo con el texto completo.
    """

    settings = get_settings()
    try:
        service = GBPAuditService(settings=settings, db=db)
        return await service.diagnosticar_descripcion_producto(sku=sku, item_id=item_id)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        raise HTTPException(status_code=500, detail=f"Error diagnosticando descripción GBP: {exc}") from exc


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
