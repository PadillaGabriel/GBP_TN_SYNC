import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.aplicacion.servicios.servicio_sincronizacion_stock import StockSyncService
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.configuracion import obtener_configuracion

logger = logging.getLogger(__name__)


class IntegradorScheduler:
    """Scheduler principal controlado por variables de entorno."""

    def __init__(self) -> None:
        self.settings = obtener_configuracion()
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Inicia tareas habilitadas."""

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
            self.scheduler.add_job(
                self._product_audit_tick,
                "interval",
                hours=self.settings.product_audit_interval_hours,
                id="product_audit_tick",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        if self.scheduler.get_jobs():
            self.scheduler.start()

    async def _stock_tick(self) -> None:
        """Sincroniza solo stock de productos ya mapeados en Tienda Nube."""

        with SessionLocal() as db:
            service = StockSyncService(settings=self.settings, db=db)
            result = await service.sincronizar_lote(
                limit=self.settings.stock_sync_batch_size
            )
            logger.info("stock_scheduler_tick_finished", extra={"result": result})

    async def _product_audit_tick(self) -> None:
        """Tick de auditoria/importacion de productos GBP.

        No se implementa importación automática por decisión de negocio actual.
        """

        return None


StockScheduler = IntegradorScheduler
