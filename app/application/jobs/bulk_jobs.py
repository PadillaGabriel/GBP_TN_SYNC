from __future__ import annotations

import logging
from typing import Any

from app.application.services.gbp_audit_service import GBPAuditService
from app.application.services.stock_sync_service import StockSyncService
from app.application.services.tienda_nube_category_service import TiendaNubeCategoryService
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


def _cancel_requested(job_id: int) -> bool:
    """Devuelve True si el usuario pidió cancelar el job."""

    with SessionLocal() as db:
        return SyncJobRepository(db).cancelacion_solicitada(job_id)


def _mark_cancelled(job_id: int, progreso: dict[str, object] | None = None) -> None:
    """Marca cancelación finalizada en el punto seguro actual."""

    payload = {"mensaje": "Proceso cancelado por el usuario.", "porcentaje": 100}
    if progreso:
        payload.update(progreso)
    _update_job(job_id, estado="CANCELADO", progreso=payload, finalizar=True)


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
            if _cancel_requested(job_id):
                _mark_cancelled(job_id, {
                    "procesados": total_procesados,
                    "publicables": total_publicables,
                    "bloqueados": total_bloqueados,
                    "errores": total_errores,
                    "pendientes": int(ultimo_pendiente or 0),
                })
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

        sin_avance_consecutivo = 0
        while True:
            if _cancel_requested(job_id):
                _mark_cancelled(job_id, {
                    "procesados": total_procesados,
                    "creados": total_creados,
                    "actualizados": total_actualizados,
                    "bloqueados": total_bloqueados,
                    "errores": total_errores,
                    "pendientes": pendientes,
                })
                return
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
            if procesados <= 0 or (seleccionados > 0 and int(result.get("errores") or 0) >= seleccionados):
                sin_avance_consecutivo += 1
            else:
                sin_avance_consecutivo = 0

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

            if seleccionados <= 0 or procesados <= 0 or sin_avance_consecutivo >= 1:
                if sin_avance_consecutivo >= 1 and pendientes > 0:
                    total_errores += 1
                    _update_job(
                        job_id,
                        estado="FINALIZADO_CON_ERRORES",
                        finalizar=True,
                        progreso={
                            "mensaje": "Importación detenida por falta de avance. Revisar errores de la última tanda antes de continuar.",
                            "batch_limit": batch_limit,
                            "dry_run": settings.dry_run,
                            "pendientes_iniciales": total_inicial,
                            "procesados": total_procesados,
                            "creados": total_creados,
                            "actualizados": total_actualizados,
                            "bloqueados": total_bloqueados,
                            "errores": total_errores,
                            "pendientes": pendientes,
                            "porcentaje": _percent(total_procesados, max(total_inicial, 1)),
                        },
                    )
                    return
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


async def ejecutar_job_auditar_proximos(
    *,
    job_id: int,
    batch_limit: int = 200,
    concurrency: int = 3,
) -> None:
    """Audita una tanda incremental con progreso visible."""

    settings = get_settings()
    try:
        if _cancel_requested(job_id):
            _mark_cancelled(job_id)
            return
        _update_job(
            job_id,
            estado="EN_PROCESO",
            progreso={"mensaje": "Auditando próximos productos.", "porcentaje": 5, "batch_limit": batch_limit},
            finalizar=False,
        )
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, iniciar=True)
            service = GBPAuditService(settings=settings, db=db)
            result = await service.ejecutar_auditoria_productos(
                limit=batch_limit,
                concurrency=concurrency,
                guardar_en_db=True,
                solo_no_auditados=True,
            )
            SyncAuditRepository(db).registrar(
                sku=None,
                accion="JOB_AUDITAR_PROXIMOS",
                estado="OK" if int(result.get("errores") or 0) == 0 else "OK_CON_ERRORES",
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
                "pendientes_por_auditar": int(result.get("candidatos_pendientes_auditar") or 0),
                "decisiones": result.get("decisiones") or {},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_auditar_proximos_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})


async def ejecutar_job_importar_pendientes(
    *,
    job_id: int,
    batch_limit: int = 25,
) -> None:
    """Importa una tanda de publicables pendientes con progreso visible."""

    settings = get_settings()
    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={"mensaje": "Importando pendientes.", "porcentaje": 5, "batch_limit": batch_limit, "dry_run": settings.dry_run},
            )
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.importar_prueba_tienda_nube(limit=batch_limit, confirm=True)
        _update_job(
            job_id,
            estado="FINALIZADO" if int(result.get("errores") or 0) == 0 else "FINALIZADO_CON_ERRORES",
            finalizar=True,
            progreso={
                "mensaje": "Importación de pendientes finalizada.",
                "porcentaje": 100,
                "seleccionados": int(result.get("seleccionados") or 0),
                "procesados": int(result.get("procesados") or 0),
                "creados": int(result.get("creados") or 0),
                "actualizados": int(result.get("actualizados") or 0),
                "bloqueados": int(result.get("bloqueados") or 0),
                "errores": int(result.get("errores") or 0),
                "duration_ms": int(result.get("duration_ms") or 0),
                "resultados_muestra": result.get("resultados") or {},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_importar_pendientes_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})


async def ejecutar_job_importar_sku(
    *,
    job_id: int,
    sku: str,
    forzar: bool = False,
) -> None:
    """Consulta GBP en vivo e importa/actualiza un SKU con progreso visible."""

    settings = get_settings()
    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={"mensaje": f"Consultando e importando SKU {sku}.", "porcentaje": 10, "sku": sku, "forzar": forzar},
            )
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.importar_producto_manual_tienda_nube(sku=sku, confirm=True, forzar=forzar)
        estado = "FINALIZADO" if result.get("ok") else "FINALIZADO_CON_ERRORES"
        _update_job(
            job_id,
            estado=estado,
            finalizar=True,
            progreso={
                "mensaje": f"SKU {sku}: {result.get('estado', '-')}",
                "porcentaje": 100,
                "sku": sku,
                "decision": result.get("decision"),
                "motivos": result.get("motivos") or [],
                "accion": result.get("accion"),
                "tn_product_id": result.get("tn_product_id"),
                "tn_variant_id": result.get("tn_variant_id"),
                "precio": result.get("precio"),
                "stock": result.get("stock"),
                "descripcion_largo": result.get("descripcion_largo"),
                "ejecuta_tienda_nube": result.get("ejecuta_tienda_nube"),
                "dry_run": result.get("dry_run"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_importar_sku_failed", extra={"job_id": job_id, "sku": sku})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100, "sku": sku})


async def ejecutar_job_stock_lote(
    *,
    job_id: int,
    batch_limit: int = 100,
) -> None:
    """Sincroniza stock de una tanda con progreso visible."""

    settings = get_settings()
    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": "Sincronizando stock.", "porcentaje": 5, "batch_limit": batch_limit})
            service = StockSyncService(settings=settings, db=db)
            result = await service.sincronizar_lote(limit=batch_limit)
        _update_job(job_id, estado="FINALIZADO" if int(result.get("errores") or 0) == 0 else "FINALIZADO_CON_ERRORES", finalizar=True, progreso={**result, "mensaje": "Sincronización de stock finalizada.", "porcentaje": 100})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_stock_lote_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})


async def ejecutar_job_stock_sku(
    *,
    job_id: int,
    sku: str,
) -> None:
    """Sincroniza stock de un SKU con progreso visible."""

    settings = get_settings()
    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": f"Sincronizando stock SKU {sku}.", "porcentaje": 10, "sku": sku})
            service = StockSyncService(settings=settings, db=db)
            result = await service.sincronizar_sku(sku=sku)
        _update_job(job_id, estado="FINALIZADO" if result.get("estado") != "ERROR" else "FINALIZADO_CON_ERRORES", finalizar=True, progreso={**result, "mensaje": f"Stock SKU {sku}: {result.get('estado', '-')}", "porcentaje": 100})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_stock_sku_failed", extra={"job_id": job_id, "sku": sku})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100, "sku": sku})


async def ejecutar_job_normalizar_categorias(
    *,
    job_id: int,
    confirm: bool = True,
) -> None:
    """Normaliza categorías duplicadas con progreso visible."""

    settings = get_settings()
    try:
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": "Normalizando categorías duplicadas.", "porcentaje": 10})
            service = TiendaNubeCategoryService(settings=settings, audit_repo=SyncAuditRepository(db))
            result = await service.normalizar_categorias_duplicadas(confirm=confirm)
        errores = len(result.get("errores_productos", [])) + len(result.get("errores_eliminacion", []))
        _update_job(job_id, estado="FINALIZADO" if errores == 0 else "FINALIZADO_CON_ERRORES", finalizar=True, progreso={**result, "mensaje": "Normalización de categorías finalizada.", "errores": errores, "porcentaje": 100})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_normalizar_categorias_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})


async def ejecutar_job_reauditar_decision(
    *,
    job_id: int,
    decision: str,
    batch_limit: int = 200,
) -> None:
    """Reconsulta GBP para productos bloqueados por una decisión y deja detalle persistido."""

    settings = get_settings()
    total = 0
    publicables = 0
    siguen_bloqueados = 0
    errores = 0
    detalle: list[dict[str, object]] = []
    try:
        with SessionLocal() as db:
            repo = ProductoRepository(db)
            skus = repo.listar_skus_por_decision(decision, limit=batch_limit)
            total_estimado = len(skus)
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": f"Reauditando {decision}.", "porcentaje": 0, "total": total_estimado})

        for sku in skus:
            if _cancel_requested(job_id):
                _mark_cancelled(job_id, {
                    "procesados": total,
                    "publicables": publicables,
                    "siguen_bloqueados": siguen_bloqueados,
                    "errores": errores,
                    "detalle_muestra": detalle,
                })
                return
            try:
                with SessionLocal() as db:
                    service = TiendaNubeImportService(settings=settings, db=db)
                    result = await service.importar_producto_manual_tienda_nube(sku=sku, confirm=False, forzar=False)
                    SyncAuditRepository(db).registrar(
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
                if result.get("decision") == "PUBLICABLE_AUTOMATICO":
                    publicables += 1
                else:
                    siguen_bloqueados += 1
                if len(detalle) < 30:
                    detalle.append({
                        "sku": sku,
                        "decision_nueva": result.get("decision"),
                        "motivos": result.get("motivos") or [],
                        "stock": result.get("stock"),
                        "precio": result.get("precio"),
                        "descripcion_largo": result.get("descripcion_largo"),
                    })
            except Exception as exc:  # noqa: BLE001
                errores += 1
                if len(detalle) < 30:
                    detalle.append({"sku": sku, "error": f"{type(exc).__name__}: {exc}"})
            _update_job(job_id, estado="EN_PROCESO", progreso={
                "mensaje": f"Reauditando {decision}.",
                "porcentaje": _percent(total + errores, max(total_estimado, 1)),
                "procesados": total,
                "publicables": publicables,
                "siguen_bloqueados": siguen_bloqueados,
                "errores": errores,
                "detalle_muestra": detalle,
            })
        _update_job(job_id, estado="FINALIZADO" if errores == 0 else "FINALIZADO_CON_ERRORES", finalizar=True, progreso={
            "mensaje": f"Reauditoría {decision} finalizada.",
            "porcentaje": 100,
            "procesados": total,
            "publicables": publicables,
            "siguen_bloqueados": siguen_bloqueados,
            "errores": errores,
            "detalle_muestra": detalle,
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_reauditar_decision_failed", extra={"job_id": job_id, "decision": decision})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})

async def ejecutar_job_reconciliar_tienda_nube(
    *,
    job_id: int,
    limit: int = 500,
) -> None:
    """Reconciliación de mapeos locales contra Tienda Nube como job visible."""

    settings = get_settings()
    try:
        if _cancel_requested(job_id):
            _mark_cancelled(job_id)
            return
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": "Reconciliando mapeos con Tienda Nube.", "porcentaje": 5, "limit": limit})
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.reconciliar_mapeos_tienda_nube(limit=limit)
        _update_job(job_id, estado="FINALIZADO" if int(result.get("errores") or 0) == 0 else "FINALIZADO_CON_ERRORES", finalizar=True, progreso={**result, "mensaje": "Reconciliación finalizada.", "porcentaje": 100})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_reconciliar_tn_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})


def ejecutar_job_reset_mapeos_locales(
    *,
    job_id: int,
) -> None:
    """Marca mapeos activos como eliminados externos como job visible."""

    settings = get_settings()
    try:
        if _cancel_requested(job_id):
            _mark_cancelled(job_id)
            return
        with SessionLocal() as db:
            SyncJobRepository(db).actualizar(job_id, estado="EN_PROCESO", iniciar=True, progreso={"mensaje": "Marcando mapeos locales como eliminado_externo.", "porcentaje": 20})
            service = TiendaNubeImportService(settings=settings, db=db)
            result = service.marcar_mapeos_como_eliminados_externos(confirm=True)
        _update_job(job_id, estado="FINALIZADO", finalizar=True, progreso={**result, "mensaje": "Reset de mapeos locales finalizado.", "porcentaje": 100})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_reset_mapeos_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__, progreso={"mensaje": str(exc), "porcentaje": 100})
