import logging
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.application.jobs.bulk_jobs import ejecutar_job_auditar_todo, ejecutar_job_importar_todo
from app.application.services.gbp_audit_service import GBPAuditService
from app.application.services.tienda_nube_import_service import TiendaNubeImportService
from app.application.services.stock_sync_service import StockSyncService
from app.application.services.tienda_nube_category_service import TiendaNubeCategoryService
from app.dependencies import get_db_session
from app.infrastructure.persistence.repositories import (
    DepositoRepository,
    ProductoRepository,
    SyncAuditRepository,
    SyncJobRepository,
)
from app.settings import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
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
        "productos_mapeados_locales": resumen.get("productos_mapeados_locales"),
        "productos_mapeados_eliminados": resumen.get("productos_mapeados_eliminados"),
        "productos_importados": resumen["productos_mapeados_tienda_nube"],
        "publicables_total": resumen["publicables_total"],
        "publicables_pendientes_importar": resumen["publicables_pendientes_importar"],
        "bloqueados_total": resumen["bloqueados_total"],
        "bloqueados_importados_tienda_nube": resumen["bloqueados_importados_tienda_nube"],
        "bloqueados_por_motivo": resumen["bloqueados_por_motivo"],
        "decisiones": productos.contar_por_decision(),
        "stock_sync": productos.resumen_stock_sync(),
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
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Panel operativo para gestionar decisiones de importación/publicación."""

    productos = ProductoRepository(db)
    return {
        "estado": estado,
        "limit": limit,
        "offset": offset,
        "q": q,
        "items": productos.listar_panel_decisiones(estado=estado, limit=limit, offset=offset, q=q),
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


@router.post("/decisiones/reconciliar-tn")
async def reconciliar_mapeos_tienda_nube(
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Revisa mapeos locales contra Tienda Nube y marca los borrados externamente."""

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.reconciliar_mapeos_tienda_nube(limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_RECONCILE_ENDPOINT_ERROR")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@router.post("/decisiones/mapeos/marcar-eliminados-externos")
def marcar_mapeos_eliminados_externos(
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Marca mapeos locales como eliminado_externo cuando Tienda Nube fue limpiada manualmente."""

    settings = get_settings()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return service.marcar_mapeos_como_eliminados_externos(confirm=confirm)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_MARK_EXTERNAL_DELETED_ENDPOINT_ERROR")
        return {"ok": False, "confirm": confirm, "error": f"{type(exc).__name__}: {exc}"}


@router.get("/depositos")
def listar_depositos(db: Session = Depends(get_db_session)) -> dict[str, object]:
    """Lista depositos configurados para stock de Tienda Nube."""

    depositos = DepositoRepository(db)
    return {"items": depositos.listar()}


@router.get("/panel", response_class=HTMLResponse)
def panel_home() -> RedirectResponse:
    """Entrada visual del panel administrativo."""

    return RedirectResponse(url="/admin/panel/decisiones?estado=requiere_revision&limit=100", status_code=303)


@router.get("/panel/decisiones", response_class=HTMLResponse)
def panel_decisiones(
    request: Request,
    estado: str = Query(default="requiere_revision"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    mensaje: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> HTMLResponse:
    """Panel HTML para revisar y ejecutar decisiones operativas."""

    productos = ProductoRepository(db)
    auditoria = SyncAuditRepository(db)
    jobs = SyncJobRepository(db)
    settings = get_settings()
    resumen = productos.resumen_operativo_panel()
    dashboard_data = {
        "app_env": settings.app_env,
        "dry_run": settings.dry_run,
        "stock_scheduler_enabled": settings.stock_scheduler_enabled,
        "stock_sync_interval_minutes": settings.stock_sync_interval_minutes,
        "productos_auditados": resumen["productos_auditados"],
        "productos_mapeados_tienda_nube": resumen["productos_mapeados_tienda_nube"],
        "productos_mapeados_locales": resumen.get("productos_mapeados_locales"),
        "productos_mapeados_eliminados": resumen.get("productos_mapeados_eliminados"),
        "productos_importados": resumen["productos_mapeados_tienda_nube"],
        "publicables_total": resumen["publicables_total"],
        "publicables_pendientes_importar": resumen["publicables_pendientes_importar"],
        "bloqueados_total": resumen["bloqueados_total"],
        "bloqueados_importados_tienda_nube": resumen["bloqueados_importados_tienda_nube"],
        "bloqueados_por_motivo": resumen["bloqueados_por_motivo"],
        "decisiones": productos.contar_por_decision(),
        "stock_sync": productos.resumen_stock_sync(),
        "jobs": jobs.contar_por_estado(),
        "ultimo_evento": auditoria.obtener_ultimo_evento(),
    }
    estados = [
        ("requiere_revision", "Requiere revisión"),
        ("bloqueado_importado", "Bloqueados importados"),
        ("publicable_pendiente", "Publicables pendientes"),
        ("importado", "Importados"),
        ("bloqueado", "Bloqueados"),
        ("todos", "Todos"),
        ("NO_PUBLICAR_STOCK_SIN_DISPONIBLE", "Sin stock disponible"),
        ("NO_PUBLICAR_SIN_DESCRIPCION_WEB", "Sin descripción web"),
        ("PUBLICABLE_AUTOMATICO", "Publicables"),
    ]
    items = productos.listar_panel_decisiones(estado=estado, limit=limit, offset=offset, q=q)
    prev_offset = max(offset - limit, 0)
    next_offset = offset + limit
    return templates.TemplateResponse(
        "admin/panel_decisiones.html",
        {
            "request": request,
            "dashboard": dashboard_data,
            "items": items,
            "estados": estados,
            "estado": estado,
            "limit": limit,
            "offset": offset,
            "prev_offset": prev_offset,
            "next_offset": next_offset,
            "q": q or "",
            "mensaje": mensaje,
            "settings": settings,
        },
    )


@router.post("/panel/jobs/auditar-todo")
async def panel_iniciar_job_auditar_todo(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    """Inicia auditoría total desde el panel y devuelve job_id para popup de progreso."""

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
    return JSONResponse({
        "ok": True,
        "job_id": job.id,
        "tipo": job.tipo,
        "status_url": f"/admin/panel/jobs/{job.id}",
    })


@router.post("/panel/jobs/importar-todo")
async def panel_iniciar_job_importar_todo(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    """Inicia importación total desde el panel y devuelve job_id para popup de progreso."""

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
    return JSONResponse({
        "ok": True,
        "job_id": job.id,
        "tipo": job.tipo,
        "dry_run": settings.dry_run,
        "status_url": f"/admin/panel/jobs/{job.id}",
    })


@router.get("/panel/jobs/{job_id}")
def panel_obtener_job(job_id: int, db: Session = Depends(get_db_session)) -> JSONResponse:
    """Devuelve progreso de job largo para el panel."""

    data = SyncJobRepository(db).obtener_serializado(job_id)
    if data is None:
        return JSONResponse({"ok": False, "error": "Job no encontrado"}, status_code=404)
    return JSONResponse({"ok": True, "job": data})


@router.post("/panel/importar-sku")
async def panel_importar_sku_directo(
    sku: str = Form(..., min_length=1),
    forzar: bool = Form(default=False),
    estado: str = Query(default="importado"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Busca un SKU en GBP y lo importa/actualiza en Tienda Nube desde el panel."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    result = await service.importar_producto_manual_tienda_nube(
        sku=sku.strip(),
        confirm=True,
        forzar=forzar,
    )
    mensaje = (
        f"SKU {sku}: {result.get('estado')}. "
        f"Acción: {result.get('accion', 'consulta/importación SKU')}. "
        f"Decisión: {result.get('decision', '-')}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/auditar-proximos")
async def panel_auditar_proximos_productos(
    batch_limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    estado: str = Query(default="publicable_pendiente"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: audita próximos productos no auditados, sin repetir desde el inicio."""

    settings = get_settings()
    service = GBPAuditService(settings=settings, db=db)
    result = await service.ejecutar_auditoria_productos(
        limit=batch_limit,
        concurrency=concurrency,
        guardar_en_db=True,
        solo_no_auditados=True,
    )
    mensaje = (
        f"Auditoría incremental finalizada. Procesados: {result.get('procesados', 0)}. "
        f"Publicables: {result.get('publicables', 0)}. "
        f"Bloqueados: {result.get('bloqueados', 0)}. "
        f"Pendientes por auditar: {result.get('candidatos_pendientes_auditar', 0)}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/importar-pendientes")
async def panel_importar_pendientes_tienda_nube(
    batch_limit: int = Query(default=25, ge=1, le=200),
    estado: str = Query(default="importado"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: importa productos publicables pendientes respetando reglas automáticas."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    result = await service.importar_prueba_tienda_nube(limit=batch_limit, confirm=True)
    mensaje = (
        f"Importación finalizada. Seleccionados: {result.get('seleccionados', 0)}. "
        f"Procesados: {result.get('procesados', 0)}. "
        f"Creados: {result.get('creados', 0)}. "
        f"Actualizados: {result.get('actualizados', 0)}. "
        f"Errores: {result.get('errores', 0)}."
    )
    return _panel_redirect(estado, mensaje, q=q)




@router.post("/panel/stock/run-now")
async def panel_stock_run_now(
    batch_limit: int = Query(default=100, ge=1, le=1000),
    estado: str = Query(default="importado"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Ejecuta sincronización manual de stock desde el panel."""

    settings = get_settings()
    service = StockSyncService(settings=settings, db=db)
    result = await service.sincronizar_lote(limit=batch_limit)
    mensaje = (
        f"Stock sincronizado. Seleccionados: {result.get('seleccionados', 0)}. "
        f"Actualizados: {result.get('actualizados', 0)}. "
        f"Sin cambios: {result.get('sin_cambios', 0)}. "
        f"Simulados: {result.get('simulados', 0)}. "
        f"No consultables: {result.get('stock_no_consultable', 0)}. "
        f"Errores: {result.get('errores', 0)}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/stock/run-sku")
async def panel_stock_run_sku(
    sku: str = Form(..., min_length=1),
    estado: str = Query(default="importado"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Sincroniza stock de un SKU puntual desde el panel."""

    settings = get_settings()
    service = StockSyncService(settings=settings, db=db)
    result = await service.sincronizar_sku(sku=sku.strip())
    mensaje = (
        f"Stock SKU {sku}: {result.get('estado', '-')}. "
        f"Anterior: {result.get('stock_anterior', '-')}. "
        f"Nuevo: {result.get('stock_nuevo', '-')}"
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/decisiones/reconciliar-tn")
async def panel_reconciliar_mapeos_tienda_nube(
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: verifica si los productos mapeados siguen existiendo en Tienda Nube."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    result = await service.reconciliar_mapeos_tienda_nube(limit=limit)
    mensaje = (
        f"Reconciliación finalizada. Verificados: {result.get('verificados', 0)}. "
        f"Marcados eliminado_externo: {result.get('marcados_eliminados_externos', 0)}. "
        f"Errores: {result.get('errores', 0)}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/decisiones/mapeos/marcar-eliminados-externos")
def panel_marcar_mapeos_eliminados_externos(
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: marca todos los mapeos locales como eliminados externamente."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    result = service.marcar_mapeos_como_eliminados_externos(confirm=True)
    mensaje = (
        f"Mapeos marcados como eliminado_externo: "
        f"{result.get('mapeos_marcados_eliminado_externo', 0)}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/categorias/normalizar-duplicadas")
async def panel_normalizar_categorias_duplicadas(
    confirm: bool = Query(default=True),
    estado: str = Query(default="todos"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Reasigna productos a categorias canonicas y elimina duplicados de Tienda Nube."""

    settings = get_settings()
    service = TiendaNubeCategoryService(settings=settings, audit_repo=SyncAuditRepository(db))
    result = await service.normalizar_categorias_duplicadas(confirm=confirm)
    mensaje = (
        f"Categorías normalizadas. Duplicadas detectadas: {result.get('categorias_duplicadas_detectadas', 0)}. "
        f"Productos actualizados: {result.get('productos_actualizados', 0)}. "
        f"Categorías eliminadas: {result.get('categorias_eliminadas', 0)}. "
        f"Errores: {len(result.get('errores_productos', [])) + len(result.get('errores_eliminacion', []))}."
    )
    return _panel_redirect(estado, mensaje, q=q)


@router.post("/panel/auditar-bloqueados-sin-descripcion")
async def panel_auditar_bloqueados_sin_descripcion(
    batch_limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    estado: str = Query(default="publicable_pendiente"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Reaudita bloqueados por falta de descripción para detectar descripciones nuevas en GBP."""

    settings = get_settings()
    productos = ProductoRepository(db)
    skus = productos.listar_skus_por_decision("NO_PUBLICAR_SIN_DESCRIPCION_WEB", limit=batch_limit)
    service = TiendaNubeImportService(settings=settings, db=db)
    procesados = 0
    publicables = 0
    errores = 0
    for sku in skus:
        result = await service.importar_producto_manual_tienda_nube(sku=sku, confirm=False, forzar=False)
        procesados += 1
        if result.get("decision") == "PUBLICABLE_AUTOMATICO":
            publicables += 1
        if not result.get("ok"):
            errores += 1
    mensaje = (
        f"Reauditoría de bloqueados sin descripción finalizada. Procesados: {procesados}. "
        f"Ahora publicables: {publicables}. Errores: {errores}."
    )
    return _panel_redirect(estado, mensaje, q=q)

@router.post("/panel/decisiones/{sku}/ocultar-tn")
async def panel_ocultar_producto_tienda_nube(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: oculta/despublica en Tienda Nube con confirmación implícita del formulario."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.ocultar_producto_tienda_nube(sku=sku, confirm=True)
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'ocultar_tienda_nube')}"
    return _panel_redirect(estado, mensaje, q)


@router.post("/panel/decisiones/{sku}/eliminar-tn")
async def panel_eliminar_producto_tienda_nube(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: elimina en Tienda Nube con confirmación implícita del formulario."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.eliminar_producto_tienda_nube(sku=sku, confirm=True)
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'eliminar_tienda_nube')}"
    return _panel_redirect(estado, mensaje, q)


@router.post("/panel/decisiones/{sku}/importar-manual")
async def panel_importar_producto_manual(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Acción visual: importa o actualiza manualmente un producto, forzando si está bloqueado."""

    settings = get_settings()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.importar_producto_manual_tienda_nube(
        sku=sku,
        confirm=True,
        forzar=True,
    )
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'importar_manual_forzada')}"
    return _panel_redirect(estado, mensaje, q)
