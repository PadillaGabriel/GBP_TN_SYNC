from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Endpoint liviano para monitoreo."""

    return {"status": "ok"}


from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.dependencias import obtener_sesion_bd


@router.get("/ready")
def readiness(db: Session = Depends(obtener_sesion_bd)) -> dict[str, str]:
    """Verifica que la API puede consultar el esquema actualizado."""
    try:
        db.execute(text("SELECT id FROM sync_jobs LIMIT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Persistencia no preparada") from exc
    return {"status": "ready"}
