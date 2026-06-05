from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_admin import router as admin_router
from app.api.routes_health import router as health_router
from app.api.routes_sync import router as sync_router
from app.infrastructure.persistence.database import create_database_schema
from app.workers.scheduler import IntegradorScheduler
from app.observability.logging import configure_logging
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos de aplicación."""

    settings = get_settings()
    configure_logging(settings.log_level)
    create_database_schema()
    scheduler = IntegradorScheduler()
    scheduler.start()
    yield


def create_app() -> FastAPI:
    """Factory principal de FastAPI."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(health_router)
    app.include_router(sync_router)
    app.include_router(admin_router)
    return app


app = create_app()
