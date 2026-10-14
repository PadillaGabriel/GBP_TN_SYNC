"""Worker durable de Railway: único consumidor de jobs de larga duración.

Ejecutar independientemente del web service: python -m app.procesos.worker.
Solo PostgreSQL está habilitado para despliegue productivo multi-proceso.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
from uuid import uuid4

from app.aplicacion.trabajos import trabajos_masivos
from app.configuracion import obtener_configuracion
from app.dependencias import construir_procesador_pedido_tienda_nube
from app.infraestructura.persistencia.base_datos import SessionLocal, engine
from app.infraestructura.persistencia.repositorios.trabajos_sincronizacion import (
    RepositorioTrabajosSincronizacion,
    TERMINALES,
)
from app.observabilidad.registro import configure_logging

logger = logging.getLogger(__name__)

# Lista de comandos explícita: nunca ejecutar nombres arbitrarios desde la base.
COMMANDS = {
    "AUDITAR_TODO_GBP": trabajos_masivos.ejecutar_job_auditar_todo,
    "IMPORTAR_TODO_TN": trabajos_masivos.ejecutar_job_importar_todo,
    "AUDITAR_PROXIMOS_GBP": trabajos_masivos.ejecutar_job_auditar_proximos,
    "IMPORTAR_PENDIENTES_TN": trabajos_masivos.ejecutar_job_importar_pendientes,
    "IMPORTAR_SKU_TN": trabajos_masivos.ejecutar_job_importar_sku,
    "STOCK_SYNC_LOTE": trabajos_masivos.ejecutar_job_stock_lote,
    "STOCK_SYNC_INCREMENTAL": trabajos_masivos.ejecutar_job_stock_incremental,
    "STOCK_SYNC_SKU": trabajos_masivos.ejecutar_job_stock_sku,
    "NORMALIZAR_CATEGORIAS_TN": trabajos_masivos.ejecutar_job_normalizar_categorias,
    "REAUDITAR_BLOQUEADOS": trabajos_masivos.ejecutar_job_reauditar_decision,
    "REAUDITAR_SIN_DESCRIPCION": trabajos_masivos.ejecutar_job_reauditar_decision,
    "RECONCILIAR_TN": trabajos_masivos.ejecutar_job_reconciliar_tienda_nube,
}


async def ejecutar(job_id: int, tipo: str, payload_raw: str | None) -> None:
    if tipo == "PEDIDO_TN_WEBHOOK":
        payload = json.loads(payload_raw or "{}")
        order_id = str(payload["order_id"])
        with SessionLocal() as db:
            procesador = construir_procesador_pedido_tienda_nube(db)
            await procesador.ejecutar(order_id)
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id, estado="FINALIZADO", finalizar=True,
                progreso={"mensaje": "Pedido procesado.", "porcentaje": 100},
            )
        return
    handler = COMMANDS.get(tipo)
    if handler is None:
        raise ValueError(f"Tipo de job no admitido: {tipo}")
    payload = json.loads(payload_raw or "{}")
    if not isinstance(payload, dict):
        raise ValueError("payload_json debe ser un objeto JSON")
    await handler(job_id=job_id, **payload)


async def _heartbeat(job_id: int, worker_id: str, stop: asyncio.Event) -> None:
    settings = obtener_configuracion()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_heartbeat_seconds)
            break
        except TimeoutError:
            with SessionLocal() as db:
                valid = RepositorioTrabajosSincronizacion(db).heartbeat(
                    job_id, worker_id, settings.worker_lease_seconds
                )
                if not valid:
                    logger.error("job_lost_lease", extra={"job_id": job_id})
                    return


async def ejecutar_siguiente(worker_id: str) -> bool:
    settings = obtener_configuracion()
    with SessionLocal() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.reclamar(worker_id, settings.worker_lease_seconds)
        if job is None:
            return False
        job_id, tipo, payload = job.id, job.tipo, job.payload_json
    logger.info("job_claimed", extra={"job_id": job_id, "type": tipo, "worker_id": worker_id})
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat(job_id, worker_id, stop))
    try:
        await ejecutar(job_id, tipo, payload)
        with SessionLocal() as db:
            repo = RepositorioTrabajosSincronizacion(db)
            job = repo.obtener(job_id)
            if job and job.estado not in TERMINALES:
                repo.actualizar(
                    job_id, estado="REQUIERE_REVISION", finalizar=True,
                    error_codigo="SIN_ESTADO_TERMINAL",
                    error_mensaje="El ejecutor terminó sin un estado terminal verificable.",
                )
    except Exception as exc:
        logger.exception("job_failed", extra={"job_id": job_id, "type": tipo})
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id, estado="REQUIERE_REVISION", finalizar=True,
                error_codigo=type(exc).__name__,
                error_mensaje="Fallo no confirmado; revisar efectos externos antes de reprocesar.",
            )
    finally:
        stop.set()
        await heartbeat
    return True


async def main() -> None:
    settings = obtener_configuracion()
    configure_logging(settings.log_level)
    if engine.dialect.name != "postgresql" and settings.app_env.lower() not in {"local", "test", "testing"}:
        raise RuntimeError("Worker en producción exige PostgreSQL")
    if settings.worker_heartbeat_seconds * 2 >= settings.worker_lease_seconds:
        raise RuntimeError("heartbeat debe ser menor que la mitad del lease")
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    logger.info("worker_started", extra={"worker_id": worker_id})
    while not stop.is_set():
        with SessionLocal() as db:
            count = RepositorioTrabajosSincronizacion(db).recuperar_interrumpidos()
            if count:
                logger.warning("orphan_jobs_quarantined", extra={"count": count})
        if not await ejecutar_siguiente(worker_id):
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
            except TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
