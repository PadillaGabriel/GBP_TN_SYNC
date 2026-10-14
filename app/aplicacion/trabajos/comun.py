"""Funciones de comun de jobs; lógica comercial preservada."""
from __future__ import annotations
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioTrabajosSincronizacion


def _percent(done: int, total: int) -> int:
    if total <= 0:
        return 100
    return max(0, min(100, int((done / total) * 100)))


def _update_job(
    job_id: int,
    *,
    estado: str | None = None,
    progreso: dict[str, object] | None = None,
    finalizar: bool = False,
    error_codigo: str | None = None,
) -> None:
    with SessionLocal() as db:
        RepositorioTrabajosSincronizacion(db).actualizar(
            job_id,
            estado=estado,
            progreso=progreso,
            finalizar=finalizar,
            error_codigo=error_codigo,
        )


def _cancel_requested(job_id: int) -> bool:
    """Devuelve True si el usuario pidió cancelar el job."""

    with SessionLocal() as db:
        return RepositorioTrabajosSincronizacion(db).cancelacion_solicitada(job_id)


def _mark_cancelled(job_id: int, progreso: dict[str, object] | None = None) -> None:
    """Marca cancelación finalizada en el punto seguro actual."""

    payload = {"mensaje": "Proceso cancelado por el usuario."}
    if progreso:
        payload.update(progreso)
    _update_job(job_id, estado="CANCELADO", progreso=payload, finalizar=True)
