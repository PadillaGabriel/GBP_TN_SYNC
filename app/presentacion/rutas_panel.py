from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.configuracion import obtener_configuracion
from app.dependencias import obtener_sesion_bd
from app.infraestructura.persistencia.repositorios import (
    RepositorioAuditoriaSincronizacion,
    RepositorioProductos,
    RepositorioTrabajosSincronizacion,
    RepositorioNormalizacionCategorias,
)

router = APIRouter(prefix="/admin/panel", tags=["panel-enterprise"])
templates = Jinja2Templates(directory="app/templates")


def _base_context(request: Request, seccion: str, titulo: str) -> dict[str, object]:
    settings = obtener_configuracion()
    return {
        "request": request,
        "seccion": seccion,
        "titulo": titulo,
        "settings": settings,
        "ahora_utc": datetime.now(UTC),
        "entorno": settings.app_env,
        "dry_run": settings.dry_run,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, db: Session = Depends(obtener_sesion_bd)) -> HTMLResponse:
    productos = RepositorioProductos(db)
    jobs = RepositorioTrabajosSincronizacion(db)
    auditoria = RepositorioAuditoriaSincronizacion(db)
    resumen = productos.resumen_operativo_panel()
    context = _base_context(request, "inicio", "Centro de operaciones")
    context.update(
        {
            "resumen": resumen,
            "decisiones": productos.contar_por_decision(),
            "stock_sync": productos.resumen_stock_sync(),
            "jobs_estado": jobs.contar_por_estado(),
            "jobs_activos": jobs.listar_activos(limit=8),
            "jobs_recientes": jobs.listar_recientes(limit=8),
            "ultimo_evento": auditoria.obtener_ultimo_evento(),
        }
    )
    return templates.TemplateResponse("enterprise/dashboard.html", context)


@router.get("/productos", response_class=HTMLResponse)
def productos(
    request: Request,
    vista: str = Query(default="todos"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    repo = RepositorioProductos(db)
    if vista == "importados":
        items = repo.listar_productos_importados(limit=limit, offset=offset)
    elif vista == "bloqueados":
        items = repo.listar_productos_bloqueados(limit=limit, offset=offset)
    else:
        items = repo.listar_panel_productos(limit=limit, offset=offset)
    context = _base_context(request, "productos", "Catálogo de productos")
    context.update(
        {
            "items": items,
            "vista": vista,
            "limit": limit,
            "offset": offset,
            "prev_offset": max(0, offset - limit),
            "next_offset": offset + limit,
            "resumen": repo.resumen_operativo_panel(),
        }
    )
    return templates.TemplateResponse("enterprise/productos.html", context)


@router.get("/importaciones", response_class=HTMLResponse)
def importaciones(
    request: Request,
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    repo = RepositorioProductos(db)
    context = _base_context(request, "importaciones", "Importación y publicación")
    context.update({"resumen": repo.resumen_operativo_panel()})
    return templates.TemplateResponse("enterprise/importaciones.html", context)


@router.get("/sincronizacion", response_class=HTMLResponse)
def sincronizacion(
    request: Request,
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    productos = RepositorioProductos(db)
    jobs = RepositorioTrabajosSincronizacion(db)
    context = _base_context(request, "sincronizacion", "Sincronización")
    context.update(
        {
            "stock_sync": productos.resumen_stock_sync(),
            "jobs_activos": jobs.listar_activos(limit=12),
            "jobs_recientes": jobs.listar_recientes(limit=12),
        }
    )
    return templates.TemplateResponse("enterprise/sincronizacion.html", context)




@router.get("/categorias", response_class=HTMLResponse)
def categorias(
    request: Request,
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    repo = RepositorioNormalizacionCategorias(db)
    context = _base_context(request, "categorias", "Normalización de categorías")
    context.update(
        {
            "aliases": repo.listar(),
            "origenes": repo.origenes_gbp(),
            "total_aliases": repo.contar(),
        }
    )
    return templates.TemplateResponse("enterprise/categorias.html", context)


@router.get("/categorias/normalizar-duplicadas", include_in_schema=False)
def categorias_normalizar_duplicadas_get() -> RedirectResponse:
    # Evita el 405 al abrir manualmente la URL de acción en el navegador.
    return RedirectResponse(url="/admin/panel/categorias", status_code=303)


@router.get("/pedidos", response_class=HTMLResponse)
def pedidos(request: Request) -> HTMLResponse:
    context = _base_context(request, "pedidos", "Pedidos Tiendanube → GBP")
    return templates.TemplateResponse("enterprise/pedidos.html", context)


@router.get("/exportaciones", response_class=HTMLResponse)
def exportaciones(request: Request) -> HTMLResponse:
    settings = obtener_configuracion()
    context = _base_context(request, "exportaciones", "Exportaciones GBP")
    context.update(
        {
            "exportaciones": [
                {
                    "id": settings.gbp_export_producto_por_item_id,
                    "nombre": "TN_PRODUCTO_POR_ITEM",
                    "uso": "Ficha interactiva dentro de GBP",
                    "compatible_ws": False,
                },
                {
                    "id": settings.gbp_export_productos_general_id,
                    "nombre": "TN_PRODUCTOS_GENERAL",
                    "uso": "Catálogo completo y consulta por SKU",
                    "compatible_ws": True,
                },
                {
                    "id": settings.gbp_export_productos_precios_id,
                    "nombre": "TN_PRODUCTOS_PRECIOS",
                    "uso": "Precios operativos",
                    "compatible_ws": True,
                },
                {
                    "id": settings.gbp_export_productos_stock_id,
                    "nombre": "TN_PRODUCTOS_STOCK",
                    "uso": "Stock operativo",
                    "compatible_ws": True,
                },
            ]
        }
    )
    return templates.TemplateResponse("enterprise/exportaciones.html", context)


@router.get("/trabajos", response_class=HTMLResponse)
def trabajos(
    request: Request,
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    repo = RepositorioTrabajosSincronizacion(db)
    context = _base_context(request, "trabajos", "Centro de trabajos")
    context.update(
        {
            "conteos": repo.contar_por_estado(),
            "activos": repo.listar_activos(limit=30),
            "recientes": repo.listar_recientes(limit=100),
        }
    )
    return templates.TemplateResponse("enterprise/trabajos.html", context)


@router.get("/auditoria", response_class=HTMLResponse)
def auditoria(
    request: Request,
    db: Session = Depends(obtener_sesion_bd),
) -> HTMLResponse:
    repo = RepositorioAuditoriaSincronizacion(db)
    context = _base_context(request, "auditoria", "Auditoría y trazabilidad")
    context.update({"ultimo_evento": repo.obtener_ultimo_evento()})
    return templates.TemplateResponse("enterprise/auditoria.html", context)


@router.get("/configuracion", response_class=HTMLResponse)
def configuracion(request: Request) -> HTMLResponse:
    settings = obtener_configuracion()
    campos = {
        "Entorno": settings.app_env,
        "Modo simulación": settings.dry_run,
        "Sincronizador de stock": settings.stock_scheduler_enabled,
        "Intervalo de stock": f"{settings.stock_sync_interval_minutes} min",
        "Importador programado": settings.import_scheduler_enabled,
        "Compañía GBP": settings.gbp_company_id,
        "Sucursal GBP": settings.pedidos_gbp_branch_id,
        "Web Service GBP": settings.gbp_web_service_id,
        "Lista de precios": settings.online_price_list_id,
        "Depósitos ecommerce": settings.ecommerce_storage_ids,
        "Exportación individual": settings.gbp_export_producto_por_item_id,
        "Exportación general": settings.gbp_export_productos_general_id,
        "Exportación precios": settings.gbp_export_productos_precios_id,
        "Exportación stock": settings.gbp_export_productos_stock_id,
        "Credencial GBP": bool(settings.gbp_username and settings.gbp_password),
        "Credencial Tiendanube": bool(
            settings.tienda_nube_store_id and settings.tienda_nube_access_token
        ),
        "Escritura pedidos GBP": settings.pedidos_escritura_gbp_habilitada,
        "Carga temporal GBP": settings.pedidos_gbp_staging_enabled,
        "Confirmación pedidos GBP": settings.pedidos_gbp_confirmation_enabled,
    }
    context = _base_context(request, "configuracion", "Configuración operativa")
    context.update({"campos": campos})
    return templates.TemplateResponse("enterprise/configuracion.html", context)
