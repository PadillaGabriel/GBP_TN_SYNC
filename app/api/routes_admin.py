import logging
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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


def _safe(value: object) -> str:
    """Escapa valores para render HTML simple sin motor de templates."""

    if value is None:
        return ""
    return escape(str(value), quote=True)


def _panel_redirect(estado: str, mensaje: str, q: str | None = None) -> RedirectResponse:
    payload = {"estado": estado, "mensaje": mensaje}
    if q:
        payload["q"] = q
    params = urlencode(payload)
    return RedirectResponse(url=f"/admin/panel/decisiones?{params}", status_code=303)


def _badge_class(decision: str) -> str:
    if decision == "PUBLICABLE_AUTOMATICO":
        return "ok"
    if decision == "SIN_VALIDAR":
        return "muted"
    return "warn"


def _render_panel_html(
    *,
    dashboard_data: dict[str, object],
    items: list[dict[str, object]],
    estado: str,
    limit: int,
    offset: int,
    mensaje: str | None,
) -> str:
    settings = get_settings()
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
    nav = "".join(
        f'<a class="tab {"active" if key == estado else ""}" '
        f'href="/admin/panel/decisiones?estado={_safe(key)}&limit={limit}">{_safe(label)}</a>'
        for key, label in estados
    )
    cards = [
        ("Ambiente", dashboard_data.get("app_env")),
        ("DRY_RUN", dashboard_data.get("dry_run")),
        ("Auditados", dashboard_data.get("productos_auditados")),
        ("Mapeados TN", dashboard_data.get("productos_mapeados_tienda_nube")),
        ("Publicables", dashboard_data.get("publicables_total")),
        ("Pendientes", dashboard_data.get("publicables_pendientes_importar")),
        ("Bloqueados", dashboard_data.get("bloqueados_total")),
        ("Bloq. importados", dashboard_data.get("bloqueados_importados_tienda_nube")),
    ]
    card_html = "".join(
        f'<div class="card"><span>{_safe(label)}</span><strong>{_safe(value)}</strong></div>'
        for label, value in cards
    )
    alert = ""
    if mensaje:
        alert = f'<div class="notice">{_safe(mensaje)}</div>'
    if not settings.dry_run:
        alert += (
            '<div class="danger">DRY_RUN=false. Las acciones Confirmar ocultar, Confirmar eliminar e Importar forzado '
            'pueden escribir en Tienda Nube.</div>'
        )

    rows = []
    for item in items:
        sku = str(item.get("sku") or "")
        decision = str(item.get("decision") or "")
        motivos = item.get("motivos_bloqueo") or []
        if isinstance(motivos, list):
            motivos_text = ", ".join(str(m) for m in motivos if m)
        else:
            motivos_text = str(motivos)
        requiere_revision = bool(item.get("requiere_revision"))
        imported = bool(item.get("ya_importado_tienda_nube"))
        actions = []
        safe_sku = _safe(sku)
        safe_estado = _safe(estado)
        if imported:
            actions.append(
                f"""<form method="post" action="/admin/panel/decisiones/{safe_sku}/ocultar-tn?estado={safe_estado}" onsubmit="return confirm('Ocultar en Tienda Nube el SKU {safe_sku}');"><button class="secondary">Ocultar</button></form>"""
            )
            actions.append(
                f"""<form method="post" action="/admin/panel/decisiones/{safe_sku}/eliminar-tn?estado={safe_estado}" onsubmit="return confirm('Eliminar en Tienda Nube el SKU {safe_sku}. Esta acción no borra la auditoría local.');"><button class="dangerbtn">Eliminar TN</button></form>"""
            )
        if (not imported) or decision != "PUBLICABLE_AUTOMATICO":
            actions.append(
                f"""<form method="post" action="/admin/panel/decisiones/{safe_sku}/importar-manual?estado={safe_estado}" onsubmit="return confirm('Importar manualmente forzado el SKU {safe_sku}');"><button>Importar forzado</button></form>"""
            )
        row_class = " class=\"review\"" if requiere_revision else ""
        rows.append(
            f"""<tr{row_class}>
                <td><strong>{safe_sku}</strong><br><small>ID GBP: {_safe(item.get('id_sistema_gbp'))}</small></td>
                <td>{_safe(item.get('titulo'))}<br><small>{_safe(item.get('categoria'))} / {_safe(item.get('subcategoria'))} / {_safe(item.get('marca'))}</small></td>
                <td><span class="badge {_badge_class(decision)}">{_safe(decision)}</span><br><small>{_safe(motivos_text)}</small></td>
                <td>{_safe(item.get('stock_publicable_tn'))}</td>
                <td>{_safe(item.get('precio_importado'))}</td>
                <td>{_safe(item.get('descripcion_largo'))}</td>
                <td>{'Sí' if imported else 'No'}<br><small>{_safe(item.get('estado_publicacion'))}</small><br><small>TN: {_safe(item.get('tn_product_id'))}</small></td>
                <td><div class="actions">{''.join(actions)}</div></td>
            </tr>"""
        )
    rows_html = "".join(rows) or '<tr><td colspan="8" class="empty">Sin productos para este filtro.</td></tr>'
    prev_offset = max(offset - limit, 0)
    next_offset = offset + limit
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GBP TN Sync | Panel de decisiones</title>
<style>
:root {{ --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#f1f3f5; --muted:#9aa4b2; --ok:#1f8f4d; --warn:#b7791f; --danger:#b42318; --blue:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }}
a {{ color:inherit; }}
header {{ padding:24px; border-bottom:1px solid var(--line); background:#11141a; position:sticky; top:0; z-index:2; }}
h1 {{ margin:0 0 8px 0; font-size:24px; }}
.sub {{ color:var(--muted); font-size:14px; }}
main {{ padding:24px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:18px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; }}
.card span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:8px; }}
.card strong {{ font-size:22px; }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin:16px 0; }}
.tab {{ text-decoration:none; padding:9px 12px; border:1px solid var(--line); border-radius:999px; color:var(--muted); background:var(--panel); font-size:13px; }}
.tab.active {{ color:white; border-color:var(--blue); background:#172554; }}
.notice {{ background:#102a43; border:1px solid #2b6cb0; padding:12px; border-radius:10px; margin:12px 0; }}
.danger {{ background:#3b0d0c; border:1px solid var(--danger); padding:12px; border-radius:10px; margin:12px 0; }}
.tablewrap {{ overflow:auto; border:1px solid var(--line); border-radius:14px; background:var(--panel); }}
table {{ width:100%; border-collapse:collapse; min-width:1120px; }}
th, td {{ padding:12px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; font-size:14px; }}
th {{ color:var(--muted); background:#12151c; position:sticky; top:98px; z-index:1; }}
small {{ color:var(--muted); }}
tr.review {{ background:rgba(180,35,24,0.10); }}
.badge {{ display:inline-block; padding:5px 8px; border-radius:999px; font-size:12px; font-weight:bold; }}
.badge.ok {{ background:rgba(31,143,77,.18); color:#7ee2a8; }}
.badge.warn {{ background:rgba(183,121,31,.18); color:#f6c56f; }}
.badge.muted {{ background:rgba(154,164,178,.18); color:#cbd5e1; }}
.actions {{ display:flex; gap:8px; flex-wrap:wrap; }}
button {{ border:0; padding:8px 10px; border-radius:8px; background:var(--blue); color:white; cursor:pointer; font-weight:bold; }}
button.secondary {{ background:#475569; }}
button.dangerbtn {{ background:var(--danger); }}
.pager {{ display:flex; gap:10px; margin-top:16px; }}
.pager a {{ padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:8px; text-decoration:none; }}
.empty {{ text-align:center; color:var(--muted); padding:32px; }}
</style>
</head>
<body>
<header>
<h1>GBP → Tienda Nube | Panel de decisiones</h1>
<div class="sub">Gestión visual de productos auditados, bloqueados, importados y acciones manuales. Servicio: /admin/panel/decisiones</div>
</header>
<main>
{alert}
<section class="cards">{card_html}</section>
<nav class="tabs">{nav}</nav>
<div class="tablewrap">
<table>
<thead><tr><th>SKU</th><th>Producto</th><th>Decisión</th><th>Stock TN</th><th>Precio</th><th>Descripción</th><th>Tienda Nube</th><th>Acciones</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
<div class="pager">
<a href="/admin/panel/decisiones?estado={_safe(estado)}&limit={limit}&offset={prev_offset}">Anterior</a>
<a href="/admin/panel/decisiones?estado={_safe(estado)}&limit={limit}&offset={next_offset}">Siguiente</a>
<a href="/admin/dashboard">JSON dashboard</a>
</div>
</main>
</body>
</html>"""


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
