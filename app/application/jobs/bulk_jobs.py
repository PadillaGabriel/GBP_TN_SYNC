from __future__ import annotations

import logging
from typing import Any

from app.application.services.gbp_audit_service import GBPAuditService
from app.application.services.tienda_nube_import_service import TiendaNubeImportService
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.persistence.repositories import ProductoRepository, SyncAuditRepository, SyncJobRepository
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _percent(done: int, total: int) -> int:
    if total <= 0:
        return 100
    return max(0, min(100, int((done / total) * 100)))


def _update_job(job_id: int, *, estado: str | None = None, progreso: dict[str, object] | None = None, finalizar: bool = False, error_codigo: str | None = None) -> None:
    with SessionLocal() as db:
        SyncJobRepository(db).actualizar(
            job_id,
            estado=estado,
            progreso=progreso,
            finalizar=finalizar,
            error_codigo=error_codigo,
        )


async def ejecutar_job_auditar_todo(
    *,
    job_id: int,
    batch_limit: int = 200,
    concurrency: int = 3,
) -> None:
    """Audita todos los candidatos GBP con imagen Website pendientes, por tandas."""

    settings = get_settings()
    total_procesados = 0
    total_publicables = 0
    total_bloqueados = 0
    total_errores = 0
    ultimo_pendiente = None

    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Auditoría total iniciada.",
                    "batch_limit": batch_limit,
                    "concurrency": concurrency,
                    "procesados": 0,
                    "porcentaje": 0,
                },
            )

        while True:
            with SessionLocal() as db:
                service = GBPAuditService(settings=settings, db=db)
                result = await service.ejecutar_auditoria_productos(
                    limit=batch_limit,
                    concurrency=concurrency,
                    guardar_en_db=True,
                    solo_no_auditados=True,
                )

            procesados = int(result.get("procesados") or 0)
            pendientes_antes = int(result.get("candidatos_pendientes_auditar") or 0)
            pendientes_despues = max(pendientes_antes - procesados, 0)
            ultimo_pendiente = pendientes_despues
            total_procesados += procesados
            total_publicables += int(result.get("publicables") or 0)
            total_bloqueados += int(result.get("bloqueados") or 0)
            total_errores += int(result.get("errores") or 0) + int(result.get("errores_persistencia") or 0)
            total_estimado = total_procesados + pendientes_despues

            _update_job(
                job_id,
                estado="EN_PROCESO",
                progreso={
                    "mensaje": "Auditando productos GBP por tandas.",
                    "batch_limit": batch_limit,
                    "concurrency": concurrency,
                    "procesados": total_procesados,
                    "publicables": total_publicables,
                    "bloqueados": total_bloqueados,
                    "errores": total_errores,
                    "pendientes": pendientes_despues,
                    "porcentaje": _percent(total_procesados, total_estimado),
                    "ultima_tanda": {
                        "procesados": procesados,
                        "publicables": int(result.get("publicables") or 0),
                        "bloqueados": int(result.get("bloqueados") or 0),
                        "errores": int(result.get("errores") or 0),
                        "duration_ms": int(result.get("duration_ms") or 0),
                    },
                },
            )

            if procesados <= 0 or pendientes_despues <= 0:
                break

        _update_job(
            job_id,
            estado="FINALIZADO" if total_errores == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                "mensaje": "Auditoría total finalizada.",
                "batch_limit": batch_limit,
                "concurrency": concurrency,
                "procesados": total_procesados,
                "publicables": total_publicables,
                "bloqueados": total_bloqueados,
                "errores": total_errores,
                "pendientes": int(ultimo_pendiente or 0),
                "porcentaje": 100,
            },
        )
        with SessionLocal() as db:
            SyncAuditRepository(db).registrar(
                sku=None,
                accion="JOB_AUDITAR_TODO",
                estado="OK" if total_errores == 0 else "OK_CON_ERRORES",
                mensaje=(
                    f"procesados={total_procesados} publicables={total_publicables} "
                    f"bloqueados={total_bloqueados} errores={total_errores} pendientes={int(ultimo_pendiente or 0)}"
                ),
                metodo_gbp="GBPAuditService.ejecutar_auditoria_productos incremental",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_auditar_todo_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={
                "mensaje": f"Error en auditoría total: {type(exc).__name__}: {exc}",
                "procesados": total_procesados,
                "publicables": total_publicables,
                "bloqueados": total_bloqueados,
                "errores": total_errores + 1,
                "pendientes": int(ultimo_pendiente or 0),
                "porcentaje": _percent(total_procesados, max(total_procesados + int(ultimo_pendiente or 0), 1)),
            },
        )


async def ejecutar_job_importar_todo(
    *,
    job_id: int,
    batch_limit: int = 50,
) -> None:
    """Importa todos los productos publicables pendientes, por tandas."""

    settings = get_settings()
    total_procesados = 0
    total_creados = 0
    total_actualizados = 0
    total_bloqueados = 0
    total_errores = 0
    total_inicial = 0
    pendientes = 0

    try:
        with SessionLocal() as db:
            resumen = ProductoRepository(db).resumen_operativo_panel()
            total_inicial = int(resumen.get("publicables_pendientes_importar") or 0)
            pendientes = total_inicial
            SyncJobRepository(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Importación total iniciada.",
                    "batch_limit": batch_limit,
                    "dry_run": settings.dry_run,
                    "pendientes_iniciales": total_inicial,
                    "procesados": 0,
                    "porcentaje": 0 if total_inicial else 100,
                },
            )

        while True:
            with SessionLocal() as db:
                pendientes = int(ProductoRepository(db).resumen_operativo_panel().get("publicables_pendientes_importar") or 0)
            if pendientes <= 0:
                break

            with SessionLocal() as db:
                service = TiendaNubeImportService(settings=settings, db=db)
                result = await service.importar_prueba_tienda_nube(limit=batch_limit, confirm=True)

            seleccionados = int(result.get("seleccionados") or 0)
            procesados = int(result.get("procesados") or 0)
            total_procesados += procesados
            total_creados += int(result.get("creados") or 0)
            total_actualizados += int(result.get("actualizados") or 0)
            total_bloqueados += int(result.get("bloqueados") or 0)
            total_errores += int(result.get("errores") or 0)

            with SessionLocal() as db:
                pendientes = int(ProductoRepository(db).resumen_operativo_panel().get("publicables_pendientes_importar") or 0)

            _update_job(
                job_id,
                estado="EN_PROCESO",
                progreso={
                    "mensaje": "Importando productos pendientes por tandas.",
                    "batch_limit": batch_limit,
                    "dry_run": settings.dry_run,
                    "pendientes_iniciales": total_inicial,
                    "procesados": total_procesados,
                    "creados": total_creados,
                    "actualizados": total_actualizados,
                    "bloqueados": total_bloqueados,
                    "errores": total_errores,
                    "pendientes": pendientes,
                    "porcentaje": _percent(total_procesados, max(total_inicial, total_procesados + pendientes)),
                    "ultima_tanda": {
                        "seleccionados": seleccionados,
                        "procesados": procesados,
                        "creados": int(result.get("creados") or 0),
                        "actualizados": int(result.get("actualizados") or 0),
                        "errores": int(result.get("errores") or 0),
                        "duration_ms": int(result.get("duration_ms") or 0),
                    },
                },
            )

            if seleccionados <= 0:
                break

        _update_job(
            job_id,
            estado="FINALIZADO" if total_errores == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                "mensaje": "Importación total finalizada.",
                "batch_limit": batch_limit,
                "dry_run": settings.dry_run,
                "pendientes_iniciales": total_inicial,
                "procesados": total_procesados,
                "creados": total_creados,
                "actualizados": total_actualizados,
                "bloqueados": total_bloqueados,
                "errores": total_errores,
                "pendientes": pendientes,
                "porcentaje": 100,
            },
        )
        with SessionLocal() as db:
            SyncAuditRepository(db).registrar(
                sku=None,
                accion="JOB_IMPORTAR_TODO_TN",
                estado="OK" if total_errores == 0 else "OK_CON_ERRORES",
                mensaje=(
                    f"procesados={total_procesados} creados={total_creados} actualizados={total_actualizados} "
                    f"bloqueados={total_bloqueados} errores={total_errores} pendientes={pendientes} dry_run={settings.dry_run}"
                ),
                metodo_gbp="TiendaNubeImportService.importar_prueba_tienda_nube",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_importar_todo_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={
                "mensaje": f"Error en importación total: {type(exc).__name__}: {exc}",
                "procesados": total_procesados,
                "creados": total_creados,
                "actualizados": total_actualizados,
                "bloqueados": total_bloqueados,
                "errores": total_errores + 1,
                "pendientes": pendientes,
                "porcentaje": _percent(total_procesados, max(total_inicial, 1)),
            },
        )
