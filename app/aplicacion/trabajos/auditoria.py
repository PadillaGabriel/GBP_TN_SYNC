"""Funciones de auditoria de jobs; lógica comercial preservada."""
from __future__ import annotations
import logging
from app.aplicacion.trabajos.comun import _cancel_requested, _mark_cancelled, _percent, _update_job
from app.aplicacion.servicios.servicio_auditoria_gbp import GBPAuditService
from app.aplicacion.servicios.servicio_importacion_tienda_nube import TiendaNubeImportService
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioProductos, RepositorioAuditoriaSincronizacion, RepositorioTrabajosSincronizacion
from app.configuracion import obtener_configuracion
from app.dominio.decisiones_producto import es_decision_publicable
logger = logging.getLogger(__name__)


async def ejecutar_job_auditar_todo(
    *,
    job_id: int,
    batch_limit: int = 200,
    concurrency: int = 3,
) -> None:
    """Audita todos los candidatos GBP con imagen Website pendientes, por tandas."""

    settings = obtener_configuracion()
    total_procesados = 0
    total_publicables = 0
    total_bloqueados = 0
    total_errores = 0
    ultimo_pendiente = None

    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
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
            if _cancel_requested(job_id):
                _mark_cancelled(
                    job_id,
                    {
                        "procesados": total_procesados,
                        "publicables": total_publicables,
                        "bloqueados": total_bloqueados,
                        "errores": total_errores,
                        "pendientes": int(ultimo_pendiente or 0),
                    },
                )
                return
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
            total_errores += int(result.get("errores") or 0) + int(
                result.get("errores_persistencia") or 0
            )
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
            RepositorioAuditoriaSincronizacion(db).registrar(
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
                "porcentaje": _percent(
                    total_procesados,
                    max(total_procesados + int(ultimo_pendiente or 0), 1),
                ),
            },
        )


async def ejecutar_job_auditar_proximos(
    *,
    job_id: int,
    batch_limit: int = 200,
    concurrency: int = 3,
) -> None:
    """Audita una tanda incremental con progreso visible."""

    settings = obtener_configuracion()
    try:
        if _cancel_requested(job_id):
            _mark_cancelled(job_id)
            return
        _update_job(
            job_id,
            estado="EN_PROCESO",
            progreso={
                "mensaje": "Auditando próximos productos.",
                "porcentaje": 5,
                "batch_limit": batch_limit,
            },
            finalizar=False,
        )
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(job_id, iniciar=True)
            service = GBPAuditService(settings=settings, db=db)
            result = await service.ejecutar_auditoria_productos(
                limit=batch_limit,
                concurrency=concurrency,
                guardar_en_db=True,
                solo_no_auditados=True,
            )
            RepositorioAuditoriaSincronizacion(db).registrar(
                sku=None,
                accion="JOB_AUDITAR_PROXIMOS",
                estado="OK"
                if int(result.get("errores") or 0) == 0
                else "OK_CON_ERRORES",
                mensaje=(
                    f"procesados={result.get('procesados', 0)} publicables={result.get('publicables', 0)} "
                    f"bloqueados={result.get('bloqueados', 0)} errores={result.get('errores', 0)} "
                    f"pendientes={result.get('candidatos_pendientes_auditar', 0)}"
                ),
                metodo_gbp="GBPAuditService.ejecutar_auditoria_productos incremental",
                duracion_ms=int(result.get("duration_ms") or 0),
            )
        _update_job(
            job_id,
            estado="FINALIZADO",
            finalizar=True,
            progreso={
                "mensaje": "Auditoría incremental finalizada.",
                "porcentaje": 100,
                "procesados": int(result.get("procesados") or 0),
                "publicables": int(result.get("publicables") or 0),
                "bloqueados": int(result.get("bloqueados") or 0),
                "errores": int(result.get("errores") or 0),
                "errores_persistencia": int(result.get("errores_persistencia") or 0),
                "pendientes_por_auditar": int(
                    result.get("candidatos_pendientes_auditar") or 0
                ),
                "decisiones": result.get("decisiones") or {},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_auditar_proximos_failed", extra={"job_id": job_id})
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )


async def ejecutar_job_reauditar_decision(
    *,
    job_id: int,
    decision: str,
    batch_limit: int = 200,
) -> None:
    """Reconsulta GBP para productos bloqueados por una decisión y deja detalle persistido."""

    settings = obtener_configuracion()
    total = 0
    publicables = 0
    siguen_bloqueados = 0
    errores = 0
    detalle: list[dict[str, object]] = []
    try:
        with SessionLocal() as db:
            repo = RepositorioProductos(db)
            skus = repo.listar_skus_por_decision(decision, limit=batch_limit)
            total_estimado = len(skus)
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": f"Reauditando {decision}.",
                    "porcentaje": 0,
                    "total": total_estimado,
                },
            )

        for sku in skus:
            if _cancel_requested(job_id):
                _mark_cancelled(
                    job_id,
                    {
                        "procesados": total,
                        "publicables": publicables,
                        "siguen_bloqueados": siguen_bloqueados,
                        "errores": errores,
                        "detalle_muestra": detalle,
                    },
                )
                return
            try:
                with SessionLocal() as db:
                    service = TiendaNubeImportService(settings=settings, db=db)
                    result = await service.importar_producto_manual_tienda_nube(
                        sku=sku, confirm=False, forzar=False
                    )
                    RepositorioAuditoriaSincronizacion(db).registrar(
                        sku=sku,
                        accion="REAUDITAR_BLOQUEADO",
                        estado="OK" if result.get("ok") else "ERROR",
                        mensaje=(
                            f"decision_anterior={decision} decision_nueva={result.get('decision')} "
                            f"motivos={result.get('motivos', [])} stock={result.get('stock')} "
                            f"precio={result.get('precio')} descripcion_largo={result.get('descripcion_largo')}"
                        ),
                        metodo_gbp="TiendaNubeImportService.importar_producto_manual_tienda_nube(confirm=False)",
                        duracion_ms=int(result.get("duration_ms") or 0),
                    )
                total += 1
                if es_decision_publicable(result.get("decision")):
                    publicables += 1
                else:
                    siguen_bloqueados += 1
                if len(detalle) < 30:
                    detalle.append(
                        {
                            "sku": sku,
                            "decision_nueva": result.get("decision"),
                            "motivos": result.get("motivos") or [],
                            "stock": result.get("stock"),
                            "precio": result.get("precio"),
                            "descripcion_largo": result.get("descripcion_largo"),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                errores += 1
                if len(detalle) < 30:
                    detalle.append(
                        {"sku": sku, "error": f"{type(exc).__name__}: {exc}"}
                    )
            _update_job(
                job_id,
                estado="EN_PROCESO",
                progreso={
                    "mensaje": f"Reauditando {decision}.",
                    "porcentaje": _percent(total + errores, max(total_estimado, 1)),
                    "procesados": total,
                    "publicables": publicables,
                    "siguen_bloqueados": siguen_bloqueados,
                    "errores": errores,
                    "detalle_muestra": detalle,
                },
            )
        _update_job(
            job_id,
            estado="FINALIZADO" if errores == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                "mensaje": f"Reauditoría {decision} finalizada.",
                "porcentaje": 100,
                "procesados": total,
                "publicables": publicables,
                "siguen_bloqueados": siguen_bloqueados,
                "errores": errores,
                "detalle_muestra": detalle,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "job_reauditar_decision_failed",
            extra={"job_id": job_id, "decision": decision},
        )
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )
