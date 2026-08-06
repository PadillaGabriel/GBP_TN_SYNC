from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import SyncAuditModel


MAPEO_TN_ESTADOS_INACTIVOS = ("eliminado_tn", "eliminado_externo")


class RepositorioAuditoriaSincronizacion:
    """Repositorio de auditoria."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def registrar(
        self,
        *,
        sku: str | None,
        accion: str,
        estado: str,
        mensaje: str,
        metodo_gbp: str | None = None,
        duracion_ms: int | None = None,
    ) -> None:
        """Registra operacion auditada."""

        self.db.add(
            SyncAuditModel(
                sku=sku,
                accion=accion,
                metodo_gbp=metodo_gbp,
                duracion_ms=duracion_ms,
                estado=estado,
                mensaje=mensaje,
            )
        )
        self.db.commit()

    def obtener_ultimo_evento(self) -> dict[str, object] | None:
        """Devuelve ultimo evento auditado."""

        event = self.db.scalars(
            select(SyncAuditModel).order_by(SyncAuditModel.created_at.desc()).limit(1)
        ).first()
        if event is None:
            return None
        return {
            "sku": event.sku,
            "accion": event.accion,
            "metodo_gbp": event.metodo_gbp,
            "duracion_ms": event.duracion_ms,
            "estado": event.estado,
            "mensaje": event.mensaje,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
