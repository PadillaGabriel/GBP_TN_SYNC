"""Scheduler separado para Railway, sin ejecución comercial dentro del proceso API."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.configuracion import obtener_configuracion
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios.trabajos_sincronizacion import RepositorioTrabajosSincronizacion
from app.observabilidad.registro import configure_logging

logger = logging.getLogger(__name__)


class IntegradorScheduler:
    def __init__(self) -> None:
        self.settings = obtener_configuracion()
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        if self.settings.stock_scheduler_enabled:
            self.scheduler.add_job(
                self._stock_tick,
                "interval",
                minutes=self.settings.stock_sync_interval_minutes,
                id="stock_sync_tick",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        if self.settings.import_scheduler_enabled:
            logger.warning("product_audit_scheduler_disabled_business_policy")
        if self.scheduler.get_jobs():
            self.scheduler.start()

    async def _stock_tick(self) -> None:
        # Identidad por ventana lógica: evita duplicar jobs si hay 2 schedulers.
        interval = self.settings.stock_sync_interval_minutes * 60
        if interval < 60:
            raise ValueError("Intervalo de stock inválido")
        bucket = int(datetime.now(UTC).timestamp()) // interval
        with SessionLocal() as db:
            job = RepositorioTrabajosSincronizacion(db).crear(
                tipo="STOCK_SYNC_LOTE",
                idempotency_key=f"stock-schedule:{interval}:{bucket}",
                payload={"batch_limit": self.settings.stock_sync_batch_size},
                progreso={"mensaje": "Sincronización programada en cola.", "porcentaje": 0},
            )
        logger.info("stock_scheduled", extra={"job_id": job.id, "bucket": bucket})


StockScheduler = IntegradorScheduler  # API histórica de importación


async def main() -> None:
    configure_logging(obtener_configuracion().log_level)
    scheduler = IntegradorScheduler()
    scheduler.start()
    try:
        await asyncio.Event().wait()
    finally:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
