from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.settings import get_settings


class IntegradorScheduler:
    """Scheduler principal controlado por variables de entorno."""

    def __init__(self) -> None:
        self.settings = get_settings()
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
            )
        if self.settings.import_scheduler_enabled:
            self.scheduler.add_job(
                self._product_audit_tick,
                "interval",
                hours=self.settings.product_audit_interval_hours,
                id="product_audit_tick",
                replace_existing=True,
                max_instances=1,
            )
        if self.scheduler.get_jobs():
            self.scheduler.start()

    async def _stock_tick(self) -> None:
        """Tick de stock frecuente."""

        return None

    async def _product_audit_tick(self) -> None:
        """Tick de auditoria/importacion de productos GBP."""

        return None

StockScheduler = IntegradorScheduler
