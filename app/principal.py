from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.presentacion.rutas_administracion import router as admin_router
from app.presentacion.rutas_salud import router as health_router
from app.presentacion.rutas_medios import router as media_router
from app.presentacion.rutas_sincronizacion import router as sync_router
from app.presentacion.rutas_pedidos import router as pedidos_router
from app.presentacion.rutas_panel import router as panel_router
from app.infraestructura.persistencia.base_datos import create_database_schema
from app.procesos.programador import IntegradorScheduler
from app.observabilidad.registro import configure_logging
from app.configuracion import obtener_configuracion


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos de aplicación."""

    settings = obtener_configuracion()
    configure_logging(settings.log_level)
    create_database_schema()
    scheduler = IntegradorScheduler()
    scheduler.start()
    yield


def create_app() -> FastAPI:
    """Factory principal de FastAPI."""

    settings = obtener_configuracion()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(health_router)
    app.include_router(sync_router)
    app.include_router(panel_router)
    app.include_router(admin_router)
    app.include_router(media_router)
    app.include_router(pedidos_router)
    return app


app = create_app()
