"""Funciones de importacion de jobs; lógica comercial preservada."""
from __future__ import annotations
import logging
from app.aplicacion.trabajos.comun import _cancel_requested, _mark_cancelled, _percent, _update_job
from app.aplicacion.servicios.servicio_importacion_tienda_nube import TiendaNubeImportService
from app.dominio.errores import TiendaNubeHTTPError
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioProductos, RepositorioAuditoriaSincronizacion, RepositorioTrabajosSincronizacion
from app.configuracion import obtener_configuracion
logger = logging.getLogger(__name__)


async def ejecutar_job_importar_todo(
    *,
    job_id: int,
    batch_limit: int = 50,
) -> None:
    """Importa todos los productos publicables pendientes, por tandas."""

    settings = obtener_configuracion()
    total_procesados = 0
    total_creados = 0
    total_actualizados = 0
    total_bloqueados = 0
    total_errores = 0
    total_inicial = 0
    pendientes = 0

    try:
        with SessionLocal() as db:
            resumen = RepositorioProductos(db).resumen_operativo_panel()
            total_inicial = int(resumen.get("publicables_pendientes_importar") or 0)
            pendientes = total_inicial
            RepositorioTrabajosSincronizacion(db).actualizar(
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
                _mark_cancelled(
                    job_id,
                    {
                        "procesados": total_procesados,
                        "creados": total_creados,
                        "actualizados": total_actualizados,
                        "bloqueados": total_bloqueados,
                        "errores": total_errores,
                        "pendientes": pendientes,
                    },
                )
                return
            with SessionLocal() as db:
                pendientes = int(
                    RepositorioProductos(db)
                    .resumen_operativo_panel()
                    .get("publicables_pendientes_importar")
                    or 0
                )
            if pendientes <= 0:
                break

            with SessionLocal() as db:
                service = TiendaNubeImportService(settings=settings, db=db)
                result = await service.importar_prueba_tienda_nube(
                    limit=batch_limit, confirm=True
                )

            seleccionados = int(result.get("seleccionados") or 0)
            procesados = int(result.get("procesados") or 0)
            total_procesados += procesados
            total_creados += int(result.get("creados") or 0)
            total_actualizados += int(result.get("actualizados") or 0)
            total_bloqueados += int(result.get("bloqueados") or 0)
            total_errores += int(result.get("errores") or 0)
            if procesados <= 0 or (
                seleccionados > 0 and int(result.get("errores") or 0) >= seleccionados
            ):
                sin_avance_consecutivo += 1
            else:
                sin_avance_consecutivo = 0

            with SessionLocal() as db:
                pendientes = int(
                    RepositorioProductos(db)
                    .resumen_operativo_panel()
                    .get("publicables_pendientes_importar")
                    or 0
                )

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
                    "porcentaje": _percent(
                        total_procesados,
                        max(total_inicial, total_procesados + pendientes),
                    ),
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
                            "porcentaje": _percent(
                                total_procesados, max(total_inicial, 1)
                            ),
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
            RepositorioAuditoriaSincronizacion(db).registrar(
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


async def ejecutar_job_importar_pendientes(
    *,
    job_id: int,
    batch_limit: int = 25,
) -> None:
    """Importa una tanda de publicables pendientes con progreso visible."""

    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": "Importando pendientes.",
                    "porcentaje": 5,
                    "batch_limit": batch_limit,
                    "dry_run": settings.dry_run,
                },
            )
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.importar_prueba_tienda_nube(
                limit=batch_limit, confirm=True
            )
        _update_job(
            job_id,
            estado="FINALIZADO"
            if int(result.get("errores") or 0) == 0
            else "FINALIZADO_CON_ERRORES",
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
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100},
        )


async def ejecutar_job_importar_sku(
    *,
    job_id: int,
    sku: str,
    forzar: bool = False,
) -> None:
    """Consulta GBP en vivo e importa/actualiza un SKU con progreso visible."""

    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id,
                estado="EN_PROCESO",
                iniciar=True,
                progreso={
                    "mensaje": f"Consultando e importando SKU {sku}.",
                    "porcentaje": 10,
                    "sku": sku,
                    "forzar": forzar,
                },
            )
            service = TiendaNubeImportService(settings=settings, db=db)
            result = await service.importar_producto_manual_tienda_nube(
                sku=sku, confirm=True, forzar=forzar
            )
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
    except TiendaNubeHTTPError as exc:
        logger.exception(
            "job_importar_sku_tienda_nube_http_error",
            extra={"job_id": job_id, "sku": sku},
        )
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={
                "mensaje": f"Tienda Nube HTTP {exc.status_code}: {exc.response_text[:500]}",
                "porcentaje": 100,
                "sku": sku,
                "tn_status_code": exc.status_code,
                "tn_url": exc.url,
                "tn_response": exc.response_text[:4000],
                "tn_request": (exc.request_body or "")[:4000],
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "job_importar_sku_failed", extra={"job_id": job_id, "sku": sku}
        )
        _update_job(
            job_id,
            estado="ERROR",
            finalizar=True,
            error_codigo=type(exc).__name__,
            progreso={"mensaje": str(exc), "porcentaje": 100, "sku": sku},
        )
