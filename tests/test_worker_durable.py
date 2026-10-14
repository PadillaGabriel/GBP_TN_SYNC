"""Regresiones de cola, cancelación, deduplicación y recuperación."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.modelos import SyncJobModel
from app.infraestructura.persistencia.repositorios.trabajos_sincronizacion import RepositorioTrabajosSincronizacion


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    yield sessions
    engine.dispose()


def test_job_durable_claim_exclusivo_e_idempotency(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        first = repo.crear(tipo="STOCK_SYNC_LOTE", idempotency_key="period:01", payload={"batch_limit": 10})
        dup = repo.crear(tipo="STOCK_SYNC_LOTE", idempotency_key="period:01", payload={"batch_limit": 10})
        assert dup.id == first.id

    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        acquired = repo.reclamar("worker-A", 120)
        assert acquired and acquired.id == first.id
        assert acquired.intentos == 1

    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        assert repo.reclamar("worker-B", 120) is None
        assert repo.heartbeat(first.id, "worker-B", 120) is False
        assert repo.heartbeat(first.id, "worker-A", 120) is True
        repo.actualizar(first.id, estado="FINALIZADO", finalizar=True, progreso={"porcentaje":100})
        assert repo.reclamar("worker-B", 120) is None


def test_cancelacion_pendiente_impide_claim(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.crear(tipo="IMPORTAR_TODO_TN")
        cancelled = repo.solicitar_cancelacion(job.id)
        assert cancelled.estado == "CANCELADO"
        assert repo.reclamar("worker-A", 120) is None


def test_cancelacion_activa_no_se_pierde_en_checkpoint(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.crear(tipo="IMPORTAR_TODO_TN")
        repo.reclamar("worker-A", 120)
        repo.solicitar_cancelacion(job.id)
        repo.actualizar(job.id, estado="EN_PROCESO", progreso={"procesados": 2})
        assert repo.obtener(job.id).estado == "CANCELACION_SOLICITADA"
        repo.actualizar(job.id, estado="CANCELADO", finalizar=True)
        assert repo.obtener(job.id).estado == "CANCELADO"


def test_lease_vencido_cuarentena_sin_reintento_automatico(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.crear(tipo="PEDIDO_TN_WEBHOOK", payload={"order_id":"10"})
        repo.reclamar("worker-A", 120)
        db.execute(update(SyncJobModel).where(SyncJobModel.id == job.id).values(lease_until=datetime.now(UTC)-timedelta(seconds=10)))
        db.commit()
        assert repo.recuperar_interrumpidos() == 1
        assert repo.obtener(job.id).estado == "REQUIERE_REVISION"
        assert repo.reclamar("worker-B", 120) is None
        assert repo.recuperar_interrumpidos() == 0


def test_progreso_no_sobrescribe_error(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.crear(tipo="AUDITAR_TODO_GBP")
        repo.reclamar("worker-A", 120)
        repo.actualizar(job.id, estado="ERROR", error_codigo="UPSTREAM", error_mensaje="fallo SOAP", progreso={"procesados":2,"porcentaje":20}, finalizar=True)
        serialized = repo.obtener_serializado(job.id)
        assert serialized["mensaje"] == "fallo SOAP"
        assert serialized["progreso_porcentaje"] == 20
        assert serialized["error_detalle"] == "fallo SOAP"


def test_no_acepta_transiciones_ilegales(database):
    with database() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        job = repo.crear(tipo="STOCK_SYNC_LOTE")
        with pytest.raises(ValueError, match="Transición inválida"):
            repo.actualizar(job.id, estado="FINALIZADO", finalizar=True)
        assert repo.obtener(job.id).estado == "PENDIENTE"
