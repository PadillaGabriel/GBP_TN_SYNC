"""Persistencia transaccional de ejecución, progreso y coordinación de jobs."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import SyncJobModel

TERMINALES = frozenset({"FINALIZADO", "FINALIZADO_CON_ERRORES", "ERROR", "CANCELADO", "REQUIERE_REVISION"})
ACTIVOS = frozenset({"PENDIENTE", "EN_PROCESO", "CANCELACION_SOLICITADA"})
TRANSICIONES = {
    "PENDIENTE": {"PENDIENTE", "CANCELADO"},
    "EN_PROCESO": {"EN_PROCESO", "CANCELACION_SOLICITADA", *TERMINALES},
    "CANCELACION_SOLICITADA": {"CANCELACION_SOLICITADA", *TERMINALES},
}


def _decode(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class RepositorioTrabajosSincronizacion:
    def __init__(self, db: Session) -> None:
        self.db = db

    def crear(
        self,
        *,
        tipo: str,
        sku: str | None = None,
        id_sistema_gbp: str | None = None,
        prioridad: int = 100,
        progreso: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> SyncJobModel:
        if idempotency_key:
            existente = self.db.scalar(
                select(SyncJobModel).where(SyncJobModel.idempotency_key == idempotency_key)
            )
            if existente:
                return existente
        job = SyncJobModel(
            tipo=tipo,
            estado="PENDIENTE",
            sku=sku,
            id_sistema_gbp=id_sistema_gbp,
            prioridad=prioridad,
            progreso_json=json.dumps(progreso or {}, ensure_ascii=False),
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            idempotency_key=idempotency_key,
        )
        try:
            # SAVEPOINT evita dejar la sesión inutilizable al recibir 2 webhooks concurrentes.
            with self.db.begin_nested():
                self.db.add(job)
                self.db.flush()
        except IntegrityError:
            if not idempotency_key:
                raise
            # Otro proceso pudo insertar la misma idempotency_key.
            existente = self.db.scalar(
                select(SyncJobModel).where(SyncJobModel.idempotency_key == idempotency_key)
            )
            if existente is None:
                raise
            self.db.commit()
            return existente
        self.db.commit()
        self.db.refresh(job)
        return job

    def obtener(self, job_id: int) -> SyncJobModel | None:
        return self.db.get(SyncJobModel, job_id)

    def actualizar(
        self,
        job_id: int,
        *,
        estado: str | None = None,
        progreso: dict[str, object] | None = None,
        error_codigo: str | None = None,
        error_mensaje: str | None = None,
        iniciar: bool = False,
        finalizar: bool = False,
    ) -> SyncJobModel | None:
        job = self.obtener(job_id)
        if job is None:
            return None
        if job.estado in TERMINALES:
            # Un actor antiguo o ejecución tardía no puede resucitar el job.
            return job
        if estado == "EN_PROCESO" and job.estado == "CANCELACION_SOLICITADA":
            # La cancelación cooperativa prevalece sobre un checkpoint normal.
            estado = None
        if estado is not None:
            if estado not in TRANSICIONES.get(job.estado, set()):
                raise ValueError(f"Transición inválida: {job.estado} -> {estado}")
            job.estado = estado
        if iniciar and job.started_at is None:
            job.started_at = datetime.now(UTC)
        if finalizar:
            if job.estado not in TERMINALES:
                raise ValueError("Se requiere estado terminal explícito antes de finalizar")
            job.finished_at = datetime.now(UTC)
            job.lease_until = None
            job.worker_id = None
        if error_codigo is not None:
            job.error_codigo = error_codigo
        if error_mensaje is not None:
            job.error_detalle = error_mensaje
        if progreso is not None:
            job.progreso_json = json.dumps(progreso, ensure_ascii=False)
        job.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(job)
        return job

    def reclamar(self, worker_id: str, lease_seconds: int) -> SyncJobModel | None:
        """Claim exclusivo de una fila. PostgreSQL usa SKIP LOCKED.

        Solo se aceptan estados PENDIENTE: las operaciones incompletas
        requieren reconciliación, nunca repetición ciega contra terceros.
        """
        now = datetime.now(UTC)
        query = (
            select(SyncJobModel)
            .where(SyncJobModel.estado == "PENDIENTE")
            .order_by(SyncJobModel.prioridad, SyncJobModel.created_at, SyncJobModel.id)
            .limit(1)
        )
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = self.db.scalar(query)
        if job is None:
            self.db.commit()  # libera cualquier transacción anterior de esta sesión
            return None
        job_id = job.id
        changed = self.db.execute(
            update(SyncJobModel)
            .where(SyncJobModel.id == job_id, SyncJobModel.estado == "PENDIENTE")
            .values(
                estado="EN_PROCESO", worker_id=worker_id,
                lease_until=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now, started_at=now,
                intentos=SyncJobModel.intentos + 1,
                updated_at=now,
            )
        ).rowcount
        self.db.commit()  # libera bloqueo tomado por SELECT FOR UPDATE SKIP LOCKED
        if changed != 1:
            return None
        return self.obtener(job_id)

    def heartbeat(self, job_id: int, worker_id: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        changed = self.db.execute(
            update(SyncJobModel)
            .where(
                SyncJobModel.id == job_id,
                SyncJobModel.worker_id == worker_id,
                SyncJobModel.estado.in_(("EN_PROCESO", "CANCELACION_SOLICITADA")),
            )
            .values(heartbeat_at=now, lease_until=now + timedelta(seconds=lease_seconds), updated_at=now)
        ).rowcount
        self.db.commit()
        return changed == 1

    def recuperar_interrumpidos(self) -> int:
        """Poner en cuarentena ejecuciones sin heartbeat sin duplicar escrituras externas."""
        now = datetime.now(UTC)
        affected = self.db.execute(
            update(SyncJobModel)
            .where(
                SyncJobModel.estado.in_(("EN_PROCESO", "CANCELACION_SOLICITADA")),
                SyncJobModel.lease_until.is_not(None),
                SyncJobModel.lease_until < now,
            )
            .values(
                estado="REQUIERE_REVISION", error_codigo="LEASE_EXPIRADO",
                error_detalle="Worker interrumpido. Verificar efectos externos antes de reintentar.",
                worker_id=None, lease_until=None, finished_at=now, updated_at=now,
            )
        ).rowcount
        self.db.commit()
        return affected

    def serializar(self, job: SyncJobModel | None) -> dict[str, object] | None:
        if job is None:
            return None
        progreso = _decode(job.progreso_json) or _decode(job.error_mensaje)
        if not progreso and job.error_mensaje and not job.progreso_json:
            progreso = {"mensaje": job.error_mensaje}
        try:
            porcentaje = max(0, min(100, int(float(progreso.get("porcentaje") or 0))))
        except (ValueError, TypeError, OverflowError):
            porcentaje = 0
        return {
            "id": job.id, "tipo": job.tipo, "estado": job.estado,
            "sku": job.sku, "id_sistema_gbp": job.id_sistema_gbp,
            "prioridad": job.prioridad, "intentos": job.intentos,
            "error_codigo": job.error_codigo,
            "error_detalle": job.error_detalle,
            "progreso": progreso, "progreso_porcentaje": porcentaje,
            "mensaje": progreso.get("mensaje") or job.error_detalle or "",
            "procesados": progreso.get("procesados") or 0,
            "total": progreso.get("total") or progreso.get("seleccionados") or 0,
            "errores": progreso.get("errores") or 0,
            "worker_id": job.worker_id,
            "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
            "lease_until": job.lease_until.isoformat() if job.lease_until else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    def obtener_serializado(self, job_id: int) -> dict[str, object] | None:
        return self.serializar(self.obtener(job_id))

    def solicitar_cancelacion(self, job_id: int) -> SyncJobModel | None:
        job = self.obtener(job_id)
        if job is None or job.estado in TERMINALES:
            return job
        progreso = _decode(job.progreso_json) or _decode(job.error_mensaje)
        progreso["cancelacion_solicitada"] = True
        progreso["mensaje"] = "Cancelación solicitada; se detendrá en el próximo punto seguro."
        now = datetime.now(UTC)
        pending = job.estado == "PENDIENTE"
        if pending:
            progreso["mensaje"] = "Cancelado antes de comenzar."
        # La condición SQL protege de escrituras obsoletas concurrentes.
        updated = self.db.execute(
            update(SyncJobModel)
            .where(SyncJobModel.id == job_id, SyncJobModel.estado == job.estado)
            .values(
                estado="CANCELADO" if pending else "CANCELACION_SOLICITADA",
                progreso_json=json.dumps(progreso, ensure_ascii=False),
                finished_at=now if pending else job.finished_at,
                updated_at=now,
            )
        ).rowcount
        self.db.commit()
        if updated != 1:
            self.db.expire_all()
            return self.obtener(job_id)
        self.db.refresh(job)
        return job

    def cancelacion_solicitada(self, job_id: int) -> bool:
        # refresh evita caché de identidad de una sesión SQLAlchemy larga.
        job = self.obtener(job_id)
        if job:
            self.db.refresh(job)
        return bool(job and job.estado in ("CANCELACION_SOLICITADA", "CANCELADO"))

    def listar_recientes(self, limit: int = 12) -> list[dict[str, object]]:
        rows = self.db.scalars(
            select(SyncJobModel)
            .order_by(SyncJobModel.created_at.desc().nullslast(), SyncJobModel.id.desc())
            .limit(limit)
        ).all()
        return [self.serializar(row) for row in rows]

    def listar_activos(self, limit: int = 12) -> list[dict[str, object]]:
        rows = self.db.scalars(
            select(SyncJobModel)
            .where(SyncJobModel.estado.in_(ACTIVOS))
            .order_by(SyncJobModel.created_at.desc().nullslast(), SyncJobModel.id.desc())
            .limit(limit)
        ).all()
        return [self.serializar(row) for row in rows]

    def contar_por_estado(self) -> dict[str, int]:
        rows = self.db.execute(
            select(SyncJobModel.estado, func.count(SyncJobModel.id)).group_by(SyncJobModel.estado)
        ).all()
        return {str(estado): int(count) for estado, count in rows}
