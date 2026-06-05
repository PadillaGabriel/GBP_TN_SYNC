from collections.abc import Generator

from sqlalchemy.orm import Session

from app.infrastructure.gbp.adapter import GBPAdapter
from app.infrastructure.gbp.client import GBPClient
from app.infrastructure.gbp.module16_registry import Module16Registry
from app.infrastructure.persistence.database import SessionLocal
from app.infrastructure.tienda_nube.adapter import TiendaNubeAdapter
from app.infrastructure.tienda_nube.client import TiendaNubeClient
from app.settings import get_settings


def get_db_session() -> Generator[Session, None, None]:
    """Crea una sesión de base de datos por request."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_gbp_adapter() -> GBPAdapter:
    """Devuelve adaptador GBP validado contra registro de Módulo 16."""

    settings = get_settings()
    client = GBPClient(
        base_url=settings.gbp_base_url,
        username=settings.gbp_username,
        password=settings.gbp_password,
        timeout_seconds=settings.gbp_timeout_seconds,
    )
    registry = Module16Registry(strict=settings.gbp_module16_strict)
    return GBPAdapter(client=client, registry=registry)


def get_tienda_nube_adapter() -> TiendaNubeAdapter:
    """Devuelve adaptador de Tienda Nube."""

    settings = get_settings()
    client = TiendaNubeClient(
        base_url=settings.tienda_nube_base_url,
        store_id=settings.tienda_nube_store_id,
        access_token=settings.tienda_nube_access_token,
        timeout_seconds=settings.tienda_nube_timeout_seconds,
    )
    return TiendaNubeAdapter(client=client)
