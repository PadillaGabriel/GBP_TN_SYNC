from __future__ import annotations

import logging
import time
from typing import Any

from app.infraestructura.gbp.analizador_xml import normalizar_objeto_gbp

logger = logging.getLogger(__name__)


class OperacionImportacionBase:
    def __init__(self, contexto) -> None:
        self.settings = contexto.settings
        self.db = contexto.db
        self.gbp_client = contexto.gbp_client
        self.normalizer = contexto.normalizer
        self.validation_service = contexto.validation_service
        self.productos_repo = contexto.productos_repo
        self.audit_repo = contexto.audit_repo
        self.payload_builder = contexto.payload_builder
        self.resolvedor_producto = contexto.resolvedor_producto
        self.persistidor_producto = contexto.persistidor_producto
        self.fabrica_tienda_nube = contexto.fabrica_tienda_nube


class MarcarEliminadosExternos(OperacionImportacionBase):
    def ejecutar(
        self,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Marca todos los mapeos activos como eliminados externamente.

        Usar cuando se borraron manualmente productos desde Tienda Nube y se quiere reiniciar
        la carga sin borrar auditoría ni productos fuente. No toca Tienda Nube.
        """

        started = time.perf_counter()
        if not confirm:
            return normalizar_objeto_gbp(
                {
                    "ok": False,
                    "confirm": confirm,
                    "ejecuta_tienda_nube": False,
                    "estado": "REQUIERE_CONFIRMACION",
                    "mensaje": "Enviar confirm=true para marcar los mapeos locales como eliminado_externo.",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        marcados = self.productos_repo.marcar_todos_mapeos_como_eliminados_externos()
        self.audit_repo.registrar(
            sku=None,
            accion="TN_MARK_ALL_MAPPINGS_EXTERNAL_DELETED",
            estado="OK",
            mensaje=f"mapeos_marcados_eliminado_externo={marcados}",
            metodo_gbp="RepositorioProductos.marcar_todos_mapeos_como_eliminados_externos",
            duracion_ms=int((time.perf_counter() - started) * 1000),
        )
        return normalizar_objeto_gbp(
            {
                "ok": True,
                "confirm": confirm,
                "ejecuta_tienda_nube": False,
                "estado": "OK",
                "mapeos_marcados_eliminado_externo": marcados,
                "mensaje": "Los mapeos locales quedaron como eliminado_externo. La próxima importación automática podrá seleccionar nuevamente esos SKUs si siguen publicables.",
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )
