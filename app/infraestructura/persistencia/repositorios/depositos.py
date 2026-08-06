from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import DepositoEcommerceModel


MAPEO_TN_ESTADOS_INACTIVOS = ("eliminado_tn", "eliminado_externo")


class RepositorioDepositos:
    """Repositorio de depositos habilitados para ecommerce."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def listar_habilitados(self) -> list[str]:
        """Lista stor_id habilitados para calcular stock TN."""

        rows = self.db.scalars(
            select(DepositoEcommerceModel).where(
                DepositoEcommerceModel.habilitado_tn.is_(True)
            )
        ).all()
        return [row.stor_id for row in rows]

    def listar(self) -> list[dict[str, object]]:
        """Lista depositos configurados."""

        rows = self.db.scalars(
            select(DepositoEcommerceModel).order_by(DepositoEcommerceModel.stor_id)
        ).all()
        return [
            {
                "stor_id": row.stor_id,
                "nombre": row.nombre,
                "habilitado_tn": row.habilitado_tn,
                "observacion": row.observacion,
            }
            for row in rows
        ]
