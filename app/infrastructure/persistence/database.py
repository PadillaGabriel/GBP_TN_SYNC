from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.settings import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base = declarative_base()


def create_database_schema() -> None:
    """Crea tablas en entornos simples.

    En producción se recomienda Alembic.
    """

    from app.infrastructure.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
