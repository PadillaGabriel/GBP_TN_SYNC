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


class ReconciliarMapeos(OperacionImportacionBase):
    async def ejecutar(
        self,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Verifica mapeos locales contra Tienda Nube y marca como eliminado_externo si no existen.

        No crea, no actualiza y no elimina productos en Tienda Nube. Solo corrige el estado local
        para que el panel y el selector de importación no consideren vigente una publicación borrada
        manualmente en Tienda Nube.
        """

        started = time.perf_counter()
        client = self.fabrica_tienda_nube.crear().client
        mapeos = self.productos_repo.listar_mapeos_tienda_nube(
            limit=limit, offset=offset
        )
        resumen: dict[str, Any] = {
            "ok": True,
            "limit": limit,
            "offset": offset,
            "verificados": 0,
            "existentes_tienda_nube": 0,
            "marcados_eliminados_externos": 0,
            "omitidos_sin_tn_product_id": 0,
            "errores": 0,
            "resultados": [],
            "duration_ms": None,
        }

        for mapeo in mapeos:
            if not mapeo.tn_product_id:
                resumen["omitidos_sin_tn_product_id"] += 1
                continue
            try:
                resumen["verificados"] += 1
                product = await client.get_product(mapeo.tn_product_id)
                if product is None:
                    self.productos_repo.actualizar_estado_mapeo_tienda_nube(
                        mapeo.sku, "eliminado_externo"
                    )
                    resumen["marcados_eliminados_externos"] += 1
                    resumen["resultados"].append(
                        {
                            "sku": mapeo.sku,
                            "tn_product_id": mapeo.tn_product_id,
                            "estado": "ELIMINADO_EXTERNO",
                        }
                    )
                    continue
                resumen["existentes_tienda_nube"] += 1
                resumen["resultados"].append(
                    {
                        "sku": mapeo.sku,
                        "tn_product_id": mapeo.tn_product_id,
                        "estado": "EXISTE_EN_TIENDA_NUBE",
                    }
                )
            except Exception as exc:  # noqa: BLE001 - una verificación no debe cortar el lote.
                logger.exception(
                    "tn_reconcile_mapping_failed", extra={"sku": mapeo.sku}
                )
                self.db.rollback()
                resumen["errores"] += 1
                resumen["resultados"].append(
                    {
                        "sku": mapeo.sku,
                        "tn_product_id": mapeo.tn_product_id,
                        "estado": "ERROR",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        resumen["duration_ms"] = int((time.perf_counter() - started) * 1000)
        resumen["ok"] = resumen["errores"] == 0
        self.audit_repo.registrar(
            sku=None,
            accion="TN_RECONCILE_MAPPINGS",
            estado="OK" if resumen["ok"] else "OK_CON_ERRORES",
            mensaje=(
                f"verificados={resumen['verificados']} existentes={resumen['existentes_tienda_nube']} "
                f"eliminados_externos={resumen['marcados_eliminados_externos']} errores={resumen['errores']}"
            ),
            metodo_gbp="ClienteTiendaNube.get_product",
            duracion_ms=int(resumen["duration_ms"] or 0),
        )
        return normalizar_objeto_gbp(resumen)
