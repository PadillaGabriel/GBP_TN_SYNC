from sqlalchemy import create_engine, inspect, text
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


def create_database_schema() -> None:
    """Crea las tablas necesarias en entornos simples.

    En producción se recomienda utilizar migraciones con Alembic.
    """

    from app.infraestructura.persistencia import modelos  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _aplicar_migraciones_compatibles()


def _aplicar_migraciones_compatibles() -> None:
    """Agrega columnas evolutivas sin depender de una base nueva.

    El proyecto mantiene una única migración mínima y explícita para instalaciones
    existentes. No altera datos ni recrea tablas.
    """
    inspector = inspect(engine)
    if "pedidos_externos" not in inspector.get_table_names():
        return
    existentes = {c["name"] for c in inspector.get_columns("pedidos_externos")}
    sentencias = []
    if "gbp_guid" not in existentes:
        sentencias.append(
            "ALTER TABLE pedidos_externos ADD COLUMN gbp_guid VARCHAR(100)"
        )
    if "confirmation_error" not in existentes:
        sentencias.append(
            "ALTER TABLE pedidos_externos ADD COLUMN confirmation_error TEXT"
        )
    if not sentencias:
        return
    with engine.begin() as conexion:
        for sentencia in sentencias:
            conexion.execute(text(sentencia))
