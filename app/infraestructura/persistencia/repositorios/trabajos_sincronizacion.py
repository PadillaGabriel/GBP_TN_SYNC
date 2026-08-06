from datetime import UTC, datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import SyncJobModel


MAPEO_TN_ESTADOS_INACTIVOS = ("eliminado_tn", "eliminado_externo")


class RepositorioTrabajosSincronizacion:
    """Repositorio de jobs."""

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
    ) -> SyncJobModel:
        """Crea un job persistido para ejecución larga."""

        job = SyncJobModel(
            tipo=tipo,
            estado="PENDIENTE",
            sku=sku,
            id_sistema_gbp=id_sistema_gbp,
            prioridad=prioridad,
            error_mensaje=json.dumps(progreso or {}, ensure_ascii=False),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def obtener(self, job_id: int) -> SyncJobModel | None:
        """Obtiene un job por id."""

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
        """Actualiza estado y progreso del job."""

        job = self.obtener(job_id)
        if job is None:
            return None
        if estado is not None:
            job.estado = estado
        if iniciar:
            job.started_at = datetime.now(UTC)
        if finalizar:
            job.finished_at = datetime.now(UTC)
        if error_codigo is not None:
            job.error_codigo = error_codigo
        if progreso is not None:
            job.error_mensaje = json.dumps(progreso, ensure_ascii=False)
        elif error_mensaje is not None:
            job.error_mensaje = error_mensaje
        self.db.commit()
        self.db.refresh(job)
        return job

    def serializar(self, job: SyncJobModel | None) -> dict[str, object] | None:
        """Serializa un job para API/panel."""

        if job is None:
            return None
        progreso: object = {}
        if job.error_mensaje:
            try:
                progreso = json.loads(job.error_mensaje)
            except json.JSONDecodeError:
                progreso = {"mensaje": job.error_mensaje}
        return {
            "id": job.id,
            "tipo": job.tipo,
            "estado": job.estado,
            "sku": job.sku,
            "id_sistema_gbp": job.id_sistema_gbp,
            "prioridad": job.prioridad,
            "intentos": job.intentos,
            "error_codigo": job.error_codigo,
            "progreso": progreso,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }

    def obtener_serializado(self, job_id: int) -> dict[str, object] | None:
        """Obtiene y serializa un job."""

        return self.serializar(self.obtener(job_id))

    def solicitar_cancelacion(self, job_id: int) -> SyncJobModel | None:
        """Marca un job como cancelación solicitada.

        La cancelación se respeta entre tandas o entre productos. No interrumpe
        una llamada externa que ya esté en curso.
        """

        job = self.obtener(job_id)
        if job is None:
            return None
        if job.estado in ("FINALIZADO", "FINALIZADO_CON_ERRORES", "ERROR", "CANCELADO"):
            return job
        progreso: dict[str, object] = {}
        if job.error_mensaje:
            try:
                progreso = json.loads(job.error_mensaje)
            except json.JSONDecodeError:
                progreso = {"mensaje_anterior": job.error_mensaje}
        progreso["cancelacion_solicitada"] = True
        progreso["mensaje"] = (
            "Cancelación solicitada. El proceso se detendrá al terminar la operación en curso."
        )
        job.estado = "CANCELACION_SOLICITADA"
        job.error_mensaje = json.dumps(progreso, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(job)
        return job

    def cancelacion_solicitada(self, job_id: int) -> bool:
        """Indica si un job debe detenerse en el próximo punto seguro."""

        job = self.obtener(job_id)
        return bool(job and job.estado in ("CANCELACION_SOLICITADA", "CANCELADO"))

    def listar_recientes(self, limit: int = 12) -> list[dict[str, object]]:
        """Lista jobs recientes para recuperar popups de progreso desde el panel."""

        rows = self.db.scalars(
            select(SyncJobModel)
            .order_by(
                SyncJobModel.created_at.desc().nullslast(), SyncJobModel.id.desc()
            )
            .limit(limit)
        ).all()
        return [
            item for item in (self.serializar(job) for job in rows) if item is not None
        ]

    def listar_activos(self, limit: int = 12) -> list[dict[str, object]]:
        """Lista jobs no terminales para saber qué sigue ejecutándose."""

        rows = self.db.scalars(
            select(SyncJobModel)
            .where(
                SyncJobModel.estado.in_(
                    ("PENDIENTE", "EN_PROCESO", "CANCELACION_SOLICITADA")
                )
            )
            .order_by(
                SyncJobModel.created_at.desc().nullslast(), SyncJobModel.id.desc()
            )
            .limit(limit)
        ).all()
        return [
            item for item in (self.serializar(job) for job in rows) if item is not None
        ]

    def contar_por_estado(self) -> dict[str, int]:
        """Cuenta jobs por estado."""

        rows = self.db.execute(
            select(SyncJobModel.estado, func.count(SyncJobModel.id)).group_by(
                SyncJobModel.estado
            )
        ).all()
        return {str(estado): int(count) for estado, count in rows}
