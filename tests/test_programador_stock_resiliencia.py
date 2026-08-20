import importlib
import sys
from types import ModuleType, SimpleNamespace

import httpx
import pytest


class _FakeAsyncIOScheduler:
    pass


apscheduler = ModuleType("apscheduler")
schedulers = ModuleType("apscheduler.schedulers")
asyncio_scheduler = ModuleType("apscheduler.schedulers.asyncio")
asyncio_scheduler.AsyncIOScheduler = _FakeAsyncIOScheduler
sys.modules.setdefault("apscheduler", apscheduler)
sys.modules.setdefault("apscheduler.schedulers", schedulers)
sys.modules.setdefault("apscheduler.schedulers.asyncio", asyncio_scheduler)

programador = importlib.import_module("app.procesos.programador")


class _FakeSession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_stock_tick_contiene_fallo_transitorio_gbp(monkeypatch):
    class _Service:
        def __init__(self, *, settings, db):
            self.settings = settings
            self.db = db

        async def sincronizar_lote(self, *, limit):
            raise httpx.ReadTimeout("GBP sin respuesta")

    scheduler = object.__new__(programador.IntegradorScheduler)
    scheduler.settings = SimpleNamespace(stock_sync_batch_size=50)

    monkeypatch.setattr(programador, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(programador, "StockSyncService", _Service)

    await scheduler._stock_tick()


@pytest.mark.asyncio
async def test_stock_tick_no_oculta_errores_de_programacion(monkeypatch):
    class _Service:
        def __init__(self, *, settings, db):
            self.settings = settings
            self.db = db

        async def sincronizar_lote(self, *, limit):
            raise RuntimeError("bug interno")

    scheduler = object.__new__(programador.IntegradorScheduler)
    scheduler.settings = SimpleNamespace(stock_sync_batch_size=50)

    monkeypatch.setattr(programador, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(programador, "StockSyncService", _Service)

    with pytest.raises(RuntimeError, match="bug interno"):
        await scheduler._stock_tick()
