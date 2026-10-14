"""Funciones de reconciliacion de jobs; lógica comercial preservada."""
from __future__ import annotations
import logging
from app.aplicacion.trabajos.comun import _cancel_requested, _mark_cancelled, _update_job
from app.aplicacion.servicios.servicio_importacion_tienda_nube import TiendaNubeImportService
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioTrabajosSincronizacion
from app.configuracion import obtener_configuracion
logger = logging.getLogger(__name__)


async def ejecutar_job_reconciliar_tienda_nube(
    *,
    job_id: int,
    limit: int = 500,
) -> None:
    """Reconciliación de mapeos locales contra Tienda Nube como job visible."""

    settings = obtener_configuracion()
    try:
        if _cancel_requested(job_id):
            _mark_cancelled(job_id)
            return
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Reconciliando mapeos con Tienda Nube.",
                    "porcentaje": 5,
                    "limit": limit,
                },
            )
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.reconciliar_mapeos_tienda_nube(limit=limit)
        _update_job(
            job_id,
            estado="FINALIZADO"
            if int(result.get("errores") or 0) == 0
            else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                **result,
                "mensaje": "Reconciliación finalizada.",
                "porcentaje": 100,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_reconciliar_tn_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )
