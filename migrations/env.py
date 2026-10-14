"""Migraciones versionadas; nunca ejecutar modificaciones desde el startup HTTP."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.configuracion import obtener_configuracion
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia import modelos  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", obtener_configuracion().database_url.replace('%', '%%'))
target_metadata = Base.metadata


def offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction():
        context.run_migrations()


def online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    offline()
else:
    online()
