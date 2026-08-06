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


class EliminarProducto(OperacionImportacionBase):
    async def ejecutar(
        self,
        *,
        sku: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Elimina un producto ya mapeado en Tienda Nube bajo confirmación explícita.

        Con DRY_RUN=true o confirm=False no escribe en Tienda Nube.
        No borra el mapeo local: cambia estado_publicacion a eliminado_tn.
        """

        started = time.perf_counter()
        ejecutar_tn = bool(confirm and not self.settings.dry_run)
        mapeo = self.productos_repo.obtener_mapeo_tienda_nube_por_sku(sku)
        if mapeo is None:
            return normalizar_objeto_gbp(
                {
                    "ok": False,
                    "dry_run": self.settings.dry_run,
                    "confirm": confirm,
                    "ejecuta_tienda_nube": False,
                    "sku": sku,
                    "estado": "SIN_MAPEO_TIENDA_NUBE",
                    "mensaje": "No existe mapeo local para ese SKU.",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        if not ejecutar_tn:
            return normalizar_objeto_gbp(
                {
                    "ok": True,
                    "dry_run": self.settings.dry_run,
                    "confirm": confirm,
                    "ejecuta_tienda_nube": False,
                    "sku": sku,
                    "tn_product_id": mapeo.tn_product_id,
                    "accion": "eliminar_tienda_nube",
                    "estado": "DRY_RUN"
                    if self.settings.dry_run
                    else "SIMULADO_SIN_CONFIRMACION",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        client = self.fabrica_tienda_nube.crear().client
        result = await client.delete_product(mapeo.tn_product_id)
        self.productos_repo.actualizar_estado_mapeo_tienda_nube(sku, "eliminado_tn")
        self.audit_repo.registrar(
            sku=sku,
            accion="TN_DELETE_PRODUCT_MANUAL",
            estado="OK",
            mensaje=f"tn_product_id={mapeo.tn_product_id}",
            metodo_gbp="ClienteTiendaNube.delete_product",
            duracion_ms=int((time.perf_counter() - started) * 1000),
        )
        return normalizar_objeto_gbp(
            {
                "ok": True,
                "dry_run": self.settings.dry_run,
                "confirm": confirm,
                "ejecuta_tienda_nube": True,
                "sku": sku,
                "tn_product_id": mapeo.tn_product_id,
                "accion": "eliminar_tienda_nube",
                "estado": "OK",
                "resultado_tienda_nube": result,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )
