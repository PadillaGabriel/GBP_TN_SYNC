"""Funciones de categorias de jobs; lógica comercial preservada."""
from __future__ import annotations
import logging
from app.aplicacion.trabajos.comun import _update_job
from app.aplicacion.servicios.servicio_categorias_tienda_nube import TiendaNubeCategoryService
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioAuditoriaSincronizacion, RepositorioNormalizacionCategorias, RepositorioTrabajosSincronizacion
from app.configuracion import obtener_configuracion
logger = logging.getLogger(__name__)


async def ejecutar_job_normalizar_categorias(
    *,
    job_id: int,
    confirm: bool = True,
) -> None:
    """Normaliza categorías duplicadas con progreso visible."""

    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Normalizando categorías duplicadas.",
                    "porcentaje": 10,
                },
            )
            service = TiendaNubeCategoryService(
                settings=settings,
                audit_repo=RepositorioAuditoriaSincronizacion(db),
                category_repo=RepositorioNormalizacionCategorias(db),
            )
            result = await service.normalizar_categorias_duplicadas(confirm=confirm)
        errores = len(result.get("errores_productos", [])) + len(
            result.get("errores_eliminacion", [])
        )
        _update_job(
            job_id,
            estado="FINALIZADO" if errores == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                **result,
                "mensaje": "Normalización de categorías finalizada.",
                "errores": errores,
                "porcentaje": 100,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_normalizar_categorias_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )
