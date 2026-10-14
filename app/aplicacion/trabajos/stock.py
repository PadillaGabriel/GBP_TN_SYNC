"""Funciones de stock de jobs; lógica comercial preservada."""
from __future__ import annotations
import logging
from app.aplicacion.trabajos.comun import _update_job
from app.aplicacion.servicios.servicio_sincronizacion_stock import StockSyncService
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioTrabajosSincronizacion
from app.configuracion import obtener_configuracion
logger = logging.getLogger(__name__)


async def ejecutar_job_stock_lote(
    *,
    job_id: int,
    batch_limit: int = 100,
) -> None:
    """Sincroniza stock de una tanda con progreso visible."""

    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Sincronizando stock.",
                    "porcentaje": 5,
                    "batch_limit": batch_limit,
                },
            )
            service = StockSyncService(settings=settings, db=db)

            def informar_avance_stock(avance: dict[str, object]) -> None:
                procesados = int(avance.get("procesados") or 0)
                total = int(avance.get("total") or avance.get("seleccionados") or 0)
                # Reservamos el 5% inicial para la descarga del snapshot GBP.
                porcentaje = 5 if total <= 0 else 5 + int((procesados / total) * 90)
                _update_job(
                    job_id,
                    estado="EN_PROCESO",
                    progreso={
                        **avance,
                        "mensaje": (
                            f"Sincronizando stock {procesados}/{total}"
                            + (f" · SKU {avance.get('sku_actual')}" if avance.get("sku_actual") else "")
                        ),
                        "porcentaje": max(5, min(95, porcentaje)),
                    },
                )

            result = await service.sincronizar_lote(
                limit=batch_limit,
                on_progress=informar_avance_stock,
            )
        _update_job(
            job_id,
            estado="FINALIZADO"
            if int(result.get("errores") or 0) == 0
            else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                **result,
                "mensaje": "Sincronización de stock finalizada.",
                "porcentaje": 100,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_stock_lote_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )


async def ejecutar_job_stock_sku(
    *,
    job_id: int,
    sku: str,
) -> None:
    """Sincroniza stock de un SKU con progreso visible."""

    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": f"Sincronizando stock SKU {sku}.",
                    "porcentaje": 10,
                    "sku": sku,
                },
            )
            service = StockSyncService(settings=settings, db=db)
            result = await service.sincronizar_sku(sku=sku)
        _update_job(
            job_id,
            estado="FINALIZADO"
            if result.get("estado") != "ERROR"
            else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                **result,
                "mensaje": f"Stock SKU {sku}: {result.get('estado', '-')}",
                "porcentaje": 100,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_stock_sku_failed", extra={"job_id": job_id, "sku": sku})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100, "sku": sku},
        )


async def ejecutar_job_stock_incremental(*, job_id: int, batch_limit: int = 100) -> None:
    """Job durable de exportación 15: no modifica el job de reconciliación 14."""
    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id, estado="EN_PROCESO", iniciar=True,
                progreso={"mensaje": "Consultando movimientos de stock GBP (15).", "porcentaje": 5},
            )
            service = StockSyncService(settings=settings, db=db)

            def informar(avance: dict[str, object]) -> None:
                procesados = int(avance.get("procesados") or 0)
                total = int(avance.get("total") or 0)
                porcentaje = 5 if not total else 5 + int(90 * procesados / total)
                _update_job(job_id, estado="EN_PROCESO", progreso={
                    **avance, "porcentaje": min(95, porcentaje),
                    "mensaje": f"Stock incremental {procesados}/{total}",
                })

            result = await service.sincronizar_incremental(limit=batch_limit, on_progress=informar)
        _update_job(
            job_id,
            estado="FINALIZADO" if result["errores"] == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={**result, "mensaje": "Stock incremental finalizado.", "porcentaje": 100},
        )
    except Exception as exc:
        logger.exception("job_stock_incremental_failed", extra={"job_id": job_id})
        _update_job(
            job_id, estado="ERROR", finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )
