"""El scheduler no consulta GBP ni escribe stock; solo crea un job durable."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import sys
from types import ModuleType
import importlib

# El scheduler se ejecuta en el servicio Railway con las dependencias completas;
# para la prueba de lógica de encolado se sustituye exclusivamente su adaptador.
apscheduler = ModuleType("apscheduler")
schedulers = ModuleType("apscheduler.schedulers")
asyncio_scheduler = ModuleType("apscheduler.schedulers.asyncio")
asyncio_scheduler.AsyncIOScheduler = type("FakeAsyncIOScheduler", (), {})
sys.modules.setdefault("apscheduler", apscheduler)
sys.modules.setdefault("apscheduler.schedulers", schedulers)
sys.modules.setdefault("apscheduler.schedulers.asyncio", asyncio_scheduler)
programador = importlib.import_module("app.procesos.programador")


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_stock_tick_crea_solicitud_idempotente(monkeypatch):
    created = []

    class Repo:
        def __init__(self, db):
            pass

        def crear(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(id=9)

    sched = object.__new__(programador.IntegradorScheduler)
    sched.settings = SimpleNamespace(stock_sync_batch_size=50, stock_sync_interval_minutes=10)
    monkeypatch.setattr(programador, "SessionLocal", FakeSession)
    monkeypatch.setattr(programador, "RepositorioTrabajosSincronizacion", Repo)

    await sched._stock_tick()
    await sched._stock_tick()

    assert len(created) == 2
    assert created[0]["tipo"] == "STOCK_SYNC_LOTE"
    assert created[0]["payload"] == {"batch_limit": 50}
    assert created[0]["idempotency_key"] == created[1]["idempotency_key"]


@pytest.mark.asyncio
async def test_stock_tick_no_oculta_fallo_de_persistencia(monkeypatch):
    class BrokenRepo:
        def __init__(self, db):
            pass

        def crear(self, **kwargs):
            raise RuntimeError("Base indisponible")

    sched = object.__new__(programador.IntegradorScheduler)
    sched.settings = SimpleNamespace(stock_sync_batch_size=50, stock_sync_interval_minutes=10)
    monkeypatch.setattr(programador, "SessionLocal", FakeSession)
    monkeypatch.setattr(programador, "RepositorioTrabajosSincronizacion", BrokenRepo)

    with pytest.raises(RuntimeError, match="Base indisponible"):
        await sched._stock_tick()

@pytest.mark.asyncio
async def test_stock_tick_incremental_usa_job_15_sin_romper_reconciliacion(monkeypatch):
    created = []

    class Repo:
        def __init__(self, db):
            pass

        def crear(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(id=11)

    sched = object.__new__(programador.IntegradorScheduler)
    sched.settings = SimpleNamespace(
        stock_sync_batch_size=50,
        stock_sync_interval_minutes=5,
        stock_incremental_enabled=True,
    )
    monkeypatch.setattr(programador, "SessionLocal", FakeSession)
    monkeypatch.setattr(programador, "RepositorioTrabajosSincronizacion", Repo)
    await sched._stock_tick()
    assert created[0]["tipo"] == "STOCK_SYNC_INCREMENTAL"
    assert created[0]["payload"] == {"batch_limit": 50}
    assert "incremental" in created[0]["idempotency_key"]
