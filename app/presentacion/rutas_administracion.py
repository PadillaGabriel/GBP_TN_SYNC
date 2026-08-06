import logging
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.aplicacion.trabajos.trabajos_masivos import (
    ejecutar_job_auditar_proximos,
    ejecutar_job_auditar_todo,
    ejecutar_job_importar_pendientes,
    ejecutar_job_importar_sku,
    ejecutar_job_importar_todo,
    ejecutar_job_normalizar_categorias,
    ejecutar_job_reauditar_decision,
    ejecutar_job_reconciliar_tienda_nube,
    ejecutar_job_reset_mapeos_locales,
    ejecutar_job_stock_lote,
    ejecutar_job_stock_sku,
)
from app.aplicacion.servicios.servicio_importacion_tienda_nube import (
    TiendaNubeImportService,
)
from app.dependencias import obtener_sesion_bd
from app.infraestructura.persistencia.repositorios import (
    RepositorioDepositos,
    RepositorioProductos,
    RepositorioAuditoriaSincronizacion,
    RepositorioTrabajosSincronizacion,
)
from app.configuracion import obtener_configuracion
from app.aplicacion.importacion_productos.compositor_producto_exportaciones import (
    CompositorProductoExportacionesGBP,
    ConfiguracionExportacionesProducto,
)
from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.exportaciones import ProveedorExportacionesGBP

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _panel_redirect(
    estado: str = "requiere_revision",
    mensaje: str | None = None,
    *,
    q: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> RedirectResponse:
    """Redirige al panel visual preservando filtros seguros.

    Centraliza las acciones POST del panel para evitar duplicar armado de URLs
    y para que un error en operaciones de mantenimiento no termine en 500 por
    falta de redirección.
    """

    params: dict[str, str | int] = {"estado": estado or "requiere_revision"}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if q:
        params["q"] = q
    if mensaje:
        params["mensaje"] = mensaje

    return RedirectResponse(
        url=f"/admin/panel/decisiones?{urlencode(params)}",
        status_code=303,
    )


@router.get("/dashboard")
def dashboard(db: Session = Depends(obtener_sesion_bd)) -> dict[str, object]:
    """Resumen operativo del integrador para el panel."""

    productos = RepositorioProductos(db)
    auditoria = RepositorioAuditoriaSincronizacion(db)
    jobs = RepositorioTrabajosSincronizacion(db)
    settings = obtener_configuracion()
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
        "bloqueados_importados_tienda_nube": resumen[
            "bloqueados_importados_tienda_nube"
        ],
        "bloqueados_por_motivo": resumen["bloqueados_por_motivo"],
        "decisiones": productos.contar_por_decision(),
        "stock_sync": productos.resumen_stock_sync(),
        "jobs": jobs.contar_por_estado(),
        "jobs_recientes": jobs.listar_recientes(limit=10),
        "jobs_activos": jobs.listar_activos(limit=10),
        "ultimo_evento": auditoria.obtener_ultimo_evento(),
        "exportaciones_gbp": {
            "producto_individual": settings.gbp_export_producto_por_item_id,
            "productos_general": settings.gbp_export_productos_general_id,
            "precios": settings.gbp_export_productos_precios_id,
            "stock": settings.gbp_export_productos_stock_id,
        },
    }


@router.get("/exportaciones")
async def listar_exportaciones_gbp() -> dict[str, object]:
    """Prueba las exportaciones compatibles con wsExportDataById."""

    settings = obtener_configuracion()
    cliente = ClienteGBP(
        base_url=settings.gbp_base_url,
        username=settings.gbp_username,
        password=settings.gbp_password,
        timeout_seconds=max(settings.gbp_timeout_seconds, 120),
        company_id=settings.gbp_company_id,
        web_service_id=settings.gbp_web_service_id,
    )
    proveedor = ProveedorExportacionesGBP(cliente, cache_seconds=0)
    definiciones = [
        {
            "export_id": settings.gbp_export_producto_por_item_id,
            "nombre": "TN_PRODUCTO_POR_ITEM",
            "compatible_ws": False,
        },
        {
            "export_id": settings.gbp_export_productos_general_id,
            "nombre": "TN_PRODUCTOS_GENERAL",
            "compatible_ws": True,
        },
        {
            "export_id": settings.gbp_export_productos_precios_id,
            "nombre": "TN_PRODUCTOS_PRECIOS",
            "compatible_ws": True,
        },
        {
            "export_id": settings.gbp_export_productos_stock_id,
            "nombre": "TN_PRODUCTOS_STOCK",
            "compatible_ws": True,
        },
    ]
    resultados: list[dict[str, object]] = []

    for definicion in definiciones:
        export_id = int(definicion["export_id"])
        nombre = str(definicion["nombre"])
        if not definicion["compatible_ws"]:
            resultados.append(
                {
                    "export_id": export_id,
                    "nombre": nombre,
                    "ok": None,
                    "omitida": True,
                    "filas": 0,
                    "duracion_ms": None,
                    "columnas": [],
                    "detalle": "Exportación interactiva no ejecutable vía WS.",
                }
            )
            continue

        try:
            snapshot = await proveedor.ejecutar(export_id, usar_cache=False)
            resultados.append(
                {
                    "export_id": export_id,
                    "nombre": nombre,
                    "ok": True,
                    "omitida": False,
                    "filas": len(snapshot.filas),
                    "duracion_ms": snapshot.duracion_ms,
                    "columnas": list(snapshot.filas[0].keys())
                    if snapshot.filas
                    else [],
                }
            )
        except Exception as exc:  # noqa: BLE001 - diagnóstico administrativo.
            resultados.append(
                {
                    "export_id": export_id,
                    "nombre": nombre,
                    "ok": False,
                    "omitida": False,
                    "filas": 0,
                    "duracion_ms": None,
                    "columnas": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    operativas = [item for item in resultados if not item.get("omitida")]
    return {
        "ok": bool(operativas) and all(item["ok"] is True for item in operativas),
        "items": resultados,
    }


@router.get("/exportaciones/producto/{item_code}")
async def previsualizar_producto_exportado(item_code: str) -> dict[str, object]:
    """Busca por SKU la ficha completa dentro de la exportación general."""

    sku = item_code.strip()
    if not sku:
        return {"ok": False, "item_code": item_code, "error": "SKU_REQUERIDO"}

    settings = obtener_configuracion()
    cliente = ClienteGBP(
        base_url=settings.gbp_base_url,
        username=settings.gbp_username,
        password=settings.gbp_password,
        timeout_seconds=max(settings.gbp_timeout_seconds, 180),
        company_id=settings.gbp_company_id,
        web_service_id=settings.gbp_web_service_id,
    )
    proveedor = ProveedorExportacionesGBP(
        cliente, cache_seconds=settings.gbp_export_cache_seconds
    )

    try:
        compositor = CompositorProductoExportacionesGBP(
            proveedor,
            ConfiguracionExportacionesProducto(
                productos_general_id=settings.gbp_export_productos_general_id,
                precios_id=settings.gbp_export_productos_precios_id,
                stock_id=settings.gbp_export_productos_stock_id,
                lista_precio_id=str(settings.online_price_list_id),
                deposito_id=str(settings.ecommerce_primary_storage_id),
            ),
        )
        producto = await compositor.obtener_por_sku(sku, usar_cache=True)
        return {
            "ok": True,
            "export_id": settings.gbp_export_productos_general_id,
            "export_ids_fuentes": {
                "general": settings.gbp_export_productos_general_id,
                "precios": settings.gbp_export_productos_precios_id,
                "stock": settings.gbp_export_productos_stock_id,
            },
            "item_code": producto.sku,
            "item_id": producto.id_sistema_gbp,
            "producto": producto.model_dump(mode="json"),
            "fuentes_crudas": producto.payload_crudo,
        }
    except Exception as exc:  # noqa: BLE001 - diagnóstico administrativo.
        return {
            "ok": False,
            "item_code": sku,
            "error": type(exc).__name__,
            "detalle": str(exc),
        }


@router.get("/productos")
def listar_productos(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Lista productos con matriz de validacion visible."""

    productos = RepositorioProductos(db)
    return {
        "limit": limit,
        "offset": offset,
        "items": productos.listar_panel_productos(limit=limit, offset=offset),
    }


@router.get("/productos/importados")
def listar_importados(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Lista productos ya mapeados en Tienda Nube."""

    productos = RepositorioProductos(db)
    return {
        "limit": limit,
        "offset": offset,
        "items": productos.listar_productos_importados(limit=limit, offset=offset),
    }


@router.get("/productos/bloqueados")
def listar_bloqueados(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Lista productos bloqueados o no publicables con motivo y acción manual."""

    productos = RepositorioProductos(db)
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
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Panel operativo para gestionar decisiones de importación/publicación."""

    productos = RepositorioProductos(db)
    return {
        "estado": estado,
        "limit": limit,
        "offset": offset,
        "q": q,
        "items": productos.listar_panel_decisiones(
            estado=estado, limit=limit, offset=offset, q=q
        ),
    }


@router.post("/decisiones/productos/{sku}/ocultar-tn")
async def ocultar_producto_tienda_nube(
    sku: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Oculta/despublica en Tienda Nube un producto ya importado."""

    settings = obtener_configuracion()
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
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Elimina en Tienda Nube un producto ya importado."""

    settings = obtener_configuracion()
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
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Revisa mapeos locales contra Tienda Nube y marca los borrados externamente."""

    settings = obtener_configuracion()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return await service.reconciliar_mapeos_tienda_nube(limit=limit, offset=offset)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_RECONCILE_ENDPOINT_ERROR")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@router.post("/decisiones/mapeos/marcar-eliminados-externos")
def marcar_mapeos_eliminados_externos(
    confirm: bool = Query(default=False),
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    """Marca mapeos locales como eliminado_externo cuando Tienda Nube fue limpiada manualmente."""

    settings = obtener_configuracion()
    try:
        service = TiendaNubeImportService(settings=settings, db=db)
        return service.marcar_mapeos_como_eliminados_externos(confirm=confirm)
    except Exception as exc:  # noqa: BLE001 - diagnóstico operativo.
        logger.exception("TN_MARK_EXTERNAL_DELETED_ENDPOINT_ERROR")
        return {
            "ok": False,
            "confirm": confirm,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.get("/depositos")
def listar_depositos(db: Session = Depends(obtener_sesion_bd)) -> dict[str, object]:
    """Lista depositos configurados para stock de Tienda Nube."""

    depositos = RepositorioDepositos(db)
    return {"items": depositos.listar()}


@router.get("/panel-legacy", response_class=HTMLResponse)
def panel_home() -> RedirectResponse:
    """Entrada visual del panel administrativo."""

    return RedirectResponse(
        url="/admin/panel",
        status_code=303,
    )


@router.get("/panel-legacy/decisiones", response_class=HTMLResponse)
def panel_decisiones(
    request: Request,
    estado: str = Query(default="requiere_revision"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    mensaje: str | None = Query(default=None),
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    """Panel HTML para revisar y ejecutar decisiones operativas."""

    productos = RepositorioProductos(db)
    auditoria = RepositorioAuditoriaSincronizacion(db)
    jobs = RepositorioTrabajosSincronizacion(db)
    settings = obtener_configuracion()
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
        "bloqueados_importados_tienda_nube": resumen[
            "bloqueados_importados_tienda_nube"
        ],
        "bloqueados_por_motivo": resumen["bloqueados_por_motivo"],
        "decisiones": productos.contar_por_decision(),
        "stock_sync": productos.resumen_stock_sync(),
        "jobs": jobs.contar_por_estado(),
        "jobs_recientes": jobs.listar_recientes(limit=10),
        "jobs_activos": jobs.listar_activos(limit=10),
        "ultimo_evento": auditoria.obtener_ultimo_evento(),
        "exportaciones_gbp": {
            "producto_individual": settings.gbp_export_producto_por_item_id,
            "productos_general": settings.gbp_export_productos_general_id,
            "precios": settings.gbp_export_productos_precios_id,
            "stock": settings.gbp_export_productos_stock_id,
        },
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
        ("PUBLICABLE_AUTOMATICO", "Precio automático"),
        ("PUBLICABLE_CONSULTAR_PRECIO", "Consultar precio"),
    ]
    items = productos.listar_panel_decisiones(
        estado=estado, limit=limit, offset=offset, q=q
    )
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
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Inicia auditoría total desde el panel y devuelve job_id para popup de progreso."""

    job = RepositorioTrabajosSincronizacion(db).crear(
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
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/jobs/importar-todo")
async def panel_iniciar_job_importar_todo(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Inicia importación total desde el panel y devuelve job_id para popup de progreso."""

    settings = obtener_configuracion()
    job = RepositorioTrabajosSincronizacion(db).crear(
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
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "dry_run": settings.dry_run,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.get("/panel/jobs/{job_id}")
def panel_obtener_job(
    job_id: int, db: Session = Depends(obtener_sesion_bd)
) -> JSONResponse:
    """Devuelve progreso de job largo para el panel."""

    data = RepositorioTrabajosSincronizacion(db).obtener_serializado(job_id)
    if data is None:
        return JSONResponse(
            {"ok": False, "error": "Job no encontrado"}, status_code=404
        )
    return JSONResponse({"ok": True, "job": data})


@router.get("/panel/jobs")
def panel_listar_jobs(db: Session = Depends(obtener_sesion_bd)) -> JSONResponse:
    """Lista jobs recientes y activos para recuperar popups desde el panel."""

    repo = RepositorioTrabajosSincronizacion(db)
    return JSONResponse(
        {
            "ok": True,
            "activos": repo.listar_activos(limit=12),
            "recientes": repo.listar_recientes(limit=12),
        }
    )


@router.post("/panel/jobs/{job_id}/cancel")
def panel_cancelar_job(
    job_id: int, db: Session = Depends(obtener_sesion_bd)
) -> JSONResponse:
    """Solicita cancelación visible de un job largo."""

    repo = RepositorioTrabajosSincronizacion(db)
    job = repo.solicitar_cancelacion(job_id)
    if job is None:
        return JSONResponse(
            {"ok": False, "error": "Job no encontrado"}, status_code=404
        )
    return JSONResponse({"ok": True, "job": repo.serializar(job)})


@router.post("/panel/importar-sku")
async def panel_importar_sku_directo(
    background_tasks: BackgroundTasks,
    sku: str = Form(..., min_length=1),
    forzar: bool = Form(default=False),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Busca un SKU en GBP y lo importa/actualiza en Tienda Nube como job visible."""

    clean_sku = sku.strip()
    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="IMPORTAR_SKU_TN",
        sku=clean_sku,
        progreso={
            "mensaje": f"Job creado para importar SKU {clean_sku}.",
            "sku": clean_sku,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_importar_sku, job_id=job.id, sku=clean_sku, forzar=forzar
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/auditar-proximos")
async def panel_auditar_proximos_productos(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=200, ge=1, le=1000),
    concurrency: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Audita próximos productos como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="AUDITAR_PROXIMOS_GBP",
        progreso={
            "mensaje": "Job creado para auditoría incremental.",
            "batch_limit": batch_limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_auditar_proximos,
        job_id=job.id,
        batch_limit=batch_limit,
        concurrency=concurrency,
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/importar-pendientes")
async def panel_importar_pendientes_tienda_nube(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Importa pendientes como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="IMPORTAR_PENDIENTES_TN",
        progreso={
            "mensaje": "Job creado para importar pendientes.",
            "batch_limit": batch_limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_importar_pendientes, job_id=job.id, batch_limit=batch_limit
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/stock/run-now")
async def panel_stock_run_now(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Ejecuta sincronización manual de stock como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="STOCK_SYNC_LOTE",
        progreso={
            "mensaje": "Job creado para sincronización de stock.",
            "batch_limit": batch_limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_stock_lote, job_id=job.id, batch_limit=batch_limit
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/stock/run-sku")
async def panel_stock_run_sku(
    background_tasks: BackgroundTasks,
    sku: str = Form(..., min_length=1),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Sincroniza stock de un SKU como job visible."""

    clean_sku = sku.strip()
    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="STOCK_SYNC_SKU",
        sku=clean_sku,
        progreso={
            "mensaje": f"Job creado para stock SKU {clean_sku}.",
            "sku": clean_sku,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(ejecutar_job_stock_sku, job_id=job.id, sku=clean_sku)
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/decisiones/reconciliar-tn")
async def panel_reconciliar_mapeos_tienda_nube(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Verifica mapeos contra Tienda Nube como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="RECONCILIAR_TN",
        progreso={
            "mensaje": "Job creado para reconciliar Tienda Nube.",
            "limit": limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_reconciliar_tienda_nube, job_id=job.id, limit=limit
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/decisiones/mapeos/marcar-eliminados-externos")
def panel_marcar_mapeos_eliminados_externos(
    background_tasks: BackgroundTasks,
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Marca mapeos como eliminados externamente como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="RESET_MAPEOS_LOCALES",
        progreso={
            "mensaje": "Job creado para resetear mapeos locales.",
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(ejecutar_job_reset_mapeos_locales, job_id=job.id)
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/categorias/normalizar-duplicadas")
async def panel_normalizar_categorias_duplicadas(
    background_tasks: BackgroundTasks,
    confirm: bool = Query(default=True),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Reasigna productos a categorias canonicas y elimina duplicados como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="NORMALIZAR_CATEGORIAS_TN",
        progreso={"mensaje": "Job creado para normalizar categorías.", "porcentaje": 0},
    )
    background_tasks.add_task(
        ejecutar_job_normalizar_categorias, job_id=job.id, confirm=confirm
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/auditar-bloqueados")
async def panel_auditar_bloqueados_por_decision(
    background_tasks: BackgroundTasks,
    decision: str = Query(default="NO_PUBLICAR_SIN_DESCRIPCION_WEB"),
    batch_limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Reaudita bloqueados por decisión y muestra detalle de requisitos faltantes."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="REAUDITAR_BLOQUEADOS",
        progreso={
            "mensaje": f"Job creado para reauditar {decision}.",
            "decision": decision,
            "batch_limit": batch_limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_reauditar_decision,
        job_id=job.id,
        decision=decision,
        batch_limit=batch_limit,
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/auditar-bloqueados-sin-descripcion")
async def panel_auditar_bloqueados_sin_descripcion(
    background_tasks: BackgroundTasks,
    batch_limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(obtener_sesion_bd),
) -> JSONResponse:
    """Compatibilidad: reaudita bloqueados por falta de descripción como job visible."""

    job = RepositorioTrabajosSincronizacion(db).crear(
        tipo="REAUDITAR_SIN_DESCRIPCION",
        progreso={
            "mensaje": "Job creado para reauditar bloqueados sin descripción.",
            "decision": "NO_PUBLICAR_SIN_DESCRIPCION_WEB",
            "batch_limit": batch_limit,
            "porcentaje": 0,
        },
    )
    background_tasks.add_task(
        ejecutar_job_reauditar_decision,
        job_id=job.id,
        decision="NO_PUBLICAR_SIN_DESCRIPCION_WEB",
        batch_limit=batch_limit,
    )
    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "tipo": job.tipo,
            "status_url": f"/admin/panel/jobs/{job.id}",
        }
    )


@router.post("/panel/decisiones/{sku}/ocultar-tn")
async def panel_ocultar_producto_tienda_nube(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(obtener_sesion_bd),
) -> RedirectResponse:
    """Acción visual: oculta/despublica en Tienda Nube con confirmación implícita del formulario."""

    settings = obtener_configuracion()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.ocultar_producto_tienda_nube(sku=sku, confirm=True)
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'ocultar_tienda_nube')}"
    return _panel_redirect(estado, mensaje, q)


@router.post("/panel/decisiones/{sku}/eliminar-tn")
async def panel_eliminar_producto_tienda_nube(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(obtener_sesion_bd),
) -> RedirectResponse:
    """Acción visual: elimina en Tienda Nube con confirmación implícita del formulario."""

    settings = obtener_configuracion()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.eliminar_producto_tienda_nube(sku=sku, confirm=True)
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'eliminar_tienda_nube')}"
    return _panel_redirect(estado, mensaje, q)


@router.post("/panel/decisiones/{sku}/importar-manual")
async def panel_importar_producto_manual(
    sku: str,
    estado: str = Query(default="requiere_revision"),
    q: str | None = Query(default=None),
    db: Session = Depends(obtener_sesion_bd),
) -> RedirectResponse:
    """Acción visual: importa o actualiza manualmente un producto, forzando si está bloqueado."""

    settings = obtener_configuracion()
    service = TiendaNubeImportService(settings=settings, db=db)
    resultado = await service.importar_producto_manual_tienda_nube(
        sku=sku,
        confirm=True,
        forzar=True,
    )
    mensaje = f"SKU {sku}: {resultado.get('estado')} - {resultado.get('accion', 'importar_manual_forzada')}"
    return _panel_redirect(estado, mensaje, q)
