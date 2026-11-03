"""Trabajo durable de conciliación de variantes externas."""
from __future__ import annotations

import logging

from app.aplicacion.servicios.descubrimiento_tienda_nube import DescubrimientoTiendaNube
from app.aplicacion.trabajos.comun import _update_job
from app.configuracion import obtener_configuracion
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios import RepositorioTrabajosSincronizacion
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube

logger = logging.getLogger(__name__)


async def ejecutar_job_descubrir_tienda_nube(*, job_id: int, max_pages: int = 100) -> None:
    settings = obtener_configuracion()
    try:
        with SessionLocal() as db:
            RepositorioTrabajosSincronizacion(db).actualizar(
                job_id, estado="EN_PROCESO", iniciar=True,
                progreso={"mensaje": "Leyendo catálogo Tiendanube para descubrir variantes externas", "porcentaje": 5},
            )
            tn = ClienteTiendaNube(
                base_url=settings.tienda_nube_base_url,
                store_id=settings.tienda_nube_store_id,
                access_token=settings.tienda_nube_access_token,
                timeout_seconds=settings.tienda_nube_timeout_seconds,
            )
            service = DescubrimientoTiendaNube(db=db, tn=tn)

            def informar(avance):
                _update_job(job_id, estado="EN_PROCESO", progreso={
                    **avance, "mensaje": f"Analizadas {avance['paginas']} páginas del catálogo",
                    "porcentaje": min(90, 5 + int(avance['paginas'] / max_pages * 85)),
                })

            resultado = await service.recorrer_catalogo(max_pages=max_pages, on_progress=informar)
        _update_job(job_id, estado="FINALIZADO_CON_ERRORES" if resultado["incompleto"] or resultado["conflictos"] else "FINALIZADO", finalizar=True,
                    progreso={**resultado, "porcentaje": 100, "mensaje": "Descubrimiento terminado; revisar conflictos y cobertura de GBP"})
    except Exception as exc:
        logger.exception("descubrimiento_tn_failed", extra={"job_id": job_id})
        _update_job(job_id, estado="ERROR", finalizar=True, error_codigo=type(exc).__name__,
                    progreso={"mensaje": "Falló el descubrimiento de catálogo TN", "porcentaje": 100})
