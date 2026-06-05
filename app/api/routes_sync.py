from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.application.services.gbp_audit_service import GBPAuditService
from app.dependencies import get_db_session
from app.settings import get_settings

router = APIRouter(prefix="/sync", tags=["sync"])


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
async def ejecutar_auditoria_productos_manual() -> dict[str, object]:
    """Endpoint manual para disparar auditoria GBP completa.

    Por seguridad, la auditoría completa queda pendiente hasta validar precio
    online y depósitos ecommerce. Usar /sync/audit/gbp-test para prueba parcial.
    """

    settings = get_settings()
    return {
        "accepted": True,
        "dry_run": settings.dry_run,
        "message": "Job de auditoria aceptado. Usar /sync/audit/gbp-test para prueba parcial real.",
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
