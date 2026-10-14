from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.configuracion import obtener_configuracion

settings = obtener_configuracion()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session,
)

Base = declarative_base()


# El esquema se gestiona exclusivamente mediante Alembic (alembic upgrade head).
# La API nunca crea ni modifica tablas por iniciar el proceso.
