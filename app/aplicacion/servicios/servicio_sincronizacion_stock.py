from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.normalizador import GBPNormalizer
from app.infraestructura.gbp.exportaciones import (
    ProveedorExportacionesGBP,
    stock_desde_exportacion,
)
from app.infraestructura.gbp.analizador_xml import normalizar_objeto_gbp
from app.infraestructura.persistencia.repositorios import (
    RepositorioProductos,
    RepositorioAuditoriaSincronizacion,
)
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube
from app.configuracion import ConfiguracionAplicacion
from app.dominio.errores import TiendaNubeHTTPError

logger = logging.getLogger(__name__)


class StockSyncService:
    """Sincroniza exclusivamente stock GBP -> Tienda Nube.

    No crea productos, no toca precio, descripción, imágenes, categorías,
    publicación ni datos comerciales. Opera solo sobre mapeos activos ya
    existentes en productos_tienda_nube.
    """

    def __init__(self, *, settings: ConfiguracionAplicacion, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.productos = RepositorioProductos(db)
        self.auditoria = RepositorioAuditoriaSincronizacion(db)
        self.gbp = ClienteGBP(
            base_url=settings.gbp_base_url,
            username=settings.gbp_username,
            password=settings.gbp_password,
            timeout_seconds=settings.gbp_timeout_seconds,
            company_id=settings.gbp_company_id,
            web_service_id=settings.gbp_web_service_id,
            retry_attempts=settings.gbp_retry_attempts,
            retry_backoff_seconds=settings.gbp_retry_backoff_seconds,
        )
        self.tn = ClienteTiendaNube(
            base_url=settings.tienda_nube_base_url,
            store_id=settings.tienda_nube_store_id,
            access_token=settings.tienda_nube_access_token,
            timeout_seconds=settings.tienda_nube_timeout_seconds,
        )
        self.normalizer = GBPNormalizer()
        self.exportaciones = ProveedorExportacionesGBP(
            self.gbp, cache_seconds=settings.gbp_export_cache_seconds
        )

    async def sincronizar_lote(
        self,
        *,
        limit: int = 100,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Sincroniza stock de una tanda y opcionalmente informa avance incremental."""

        started = time.perf_counter()
        items = self.productos.listar_mapeos_activos_para_stock(limit=limit)
        resumen = self._empty_summary(limit=limit)
        resumen["seleccionados"] = len(items)
        if not items:
            resumen["ok"] = True
            resumen["duration_ms"] = int((time.perf_counter() - started) * 1000)
            return resumen

        snapshot = await self.exportaciones.ejecutar(
            self.settings.gbp_export_productos_stock_id, usar_cache=False
        )
        por_item = {
            str(row.get("item_id") or "").strip(): row for row in snapshot.filas
        }
        resultados: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            result = await self._sincronizar_item(
                item, fila_stock=por_item.get(str(item["id_sistema_gbp"]))
            )
            resultados.append(result)
            self._sumar_resultado(resumen, result)
            if on_progress is not None:
                on_progress(
                    {
                        **resumen,
                        "procesados": index,
                        "total": len(items),
                        "sku_actual": str(item.get("sku") or ""),
                    }
                )

        resumen["ok"] = resumen["errores"] == 0
        resumen["resultados_muestra"] = resultados[:20]
        resumen["duration_ms"] = int((time.perf_counter() - started) * 1000)
        self.auditoria.registrar(
            sku=None,
            accion="STOCK_SYNC_RUN_NOW",
            estado="OK" if resumen["ok"] else "OK_CON_ERRORES",
            mensaje=(
                f"seleccionados={resumen['seleccionados']} procesados={resumen['procesados']} "
                f"actualizados={resumen['actualizados']} sin_cambios={resumen['sin_cambios']} "
                f"simulados={resumen['simulados']} no_consultables={resumen['stock_no_consultable']} "
                f"mapeos_reparados={resumen['mapeos_reparados']} "
                f"mapeos_obsoletos={resumen['mapeos_obsoletos']} "
                f"errores={resumen['errores']} dry_run={self.settings.dry_run}"
            ),
            metodo_gbp="wsExportDataById(14)",
            duracion_ms=int(resumen["duration_ms"]),
        )
        return normalizar_objeto_gbp(resumen)

    async def sincronizar_sku(self, *, sku: str) -> dict[str, Any]:
        """Sincroniza stock de un SKU ya importado/mapeado."""

        started = time.perf_counter()
        item = self.productos.obtener_mapeo_activo_para_stock_por_sku(sku)
        if item is None:
            return normalizar_objeto_gbp(
                {
                    "ok": False,
                    "dry_run": self.settings.dry_run,
                    "sku": sku,
                    "estado": "NO_MAPEADO_ACTIVO",
                    "mensaje": "El SKU no tiene mapeo activo en Tienda Nube. El stock no crea productos.",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        row = await self.exportaciones.buscar_fila(
            self.settings.gbp_export_productos_stock_id,
            item_id=item["id_sistema_gbp"],
            sku=sku,
            usar_cache=False,
        )
        result = await self._sincronizar_item(item, fila_stock=row)
        result["ok"] = result.get("estado") not in {
            "ERROR",
            "STOCK_NO_CONSULTABLE",
            "MAPEO_TN_OBSOLETO",
        }
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return normalizar_objeto_gbp(result)

    def obtener_status(self) -> dict[str, Any]:
        """Devuelve estado operativo del módulo de stock."""

        return normalizar_objeto_gbp(
            {
                "ok": True,
                "dry_run": self.settings.dry_run,
                "stock_scheduler_enabled": self.settings.stock_scheduler_enabled,
                "stock_sync_interval_minutes": self.settings.stock_sync_interval_minutes,
                "stock_sync_batch_size": self.settings.stock_sync_batch_size,
                "stock_sync_concurrency": self.settings.stock_sync_concurrency,
                **self.productos.resumen_stock_sync(),
            }
        )

    async def _sincronizar_item(
        self, item: dict[str, Any], *, fila_stock: dict[str, str] | None
    ) -> dict[str, Any]:
        sku = str(item["sku"])
        producto_id = int(item["producto_fuente_id"])
        item_id = str(item["id_sistema_gbp"])
        tn_product_id = str(item["tn_product_id"])
        tn_variant_id = str(item.get("tn_variant_id") or "")
        stock_anterior = item.get("stock_publicable_tn")

        try:
            if fila_stock is None:
                raise RuntimeError("El item no está presente en TN_PRODUCTOS_STOCK")
            stock = stock_desde_exportacion(fila_stock)
            self.productos.guardar_stock(producto_id, stock)

            if not stock.consultable:
                self.auditoria.registrar(
                    sku=sku,
                    accion="STOCK_SYNC_SKU",
                    estado="STOCK_NO_CONSULTABLE",
                    mensaje="GBP no devolvió stock consultable para el depósito ecommerce configurado.",
                    metodo_gbp="wsExportDataById(14)",
                )
                return {
                    "sku": sku,
                    "estado": "STOCK_NO_CONSULTABLE",
                    "stock_anterior": stock_anterior,
                    "stock_nuevo": None,
                    "tn_product_id": tn_product_id,
                    "tn_variant_id": tn_variant_id or None,
                }

            stock_nuevo = int(stock.cantidad)
            if stock_anterior is not None and int(stock_anterior) == stock_nuevo:
                self.productos.marcar_stock_sync_tienda_nube(sku)
                self.auditoria.registrar(
                    sku=sku,
                    accion="STOCK_SYNC_SKU",
                    estado="SIN_CAMBIOS",
                    mensaje=f"Stock sin cambios: {stock_nuevo}",
                    metodo_gbp="wsExportDataById(14)",
                )
                return {
                    "sku": sku,
                    "estado": "SIN_CAMBIOS",
                    "stock_anterior": stock_anterior,
                    "stock_nuevo": stock_nuevo,
                    "tn_product_id": tn_product_id,
                    "tn_variant_id": tn_variant_id or None,
                }

            if not tn_variant_id:
                product = await self.tn.get_product(tn_product_id)
                variants = (
                    product.get("variants", []) if isinstance(product, dict) else []
                )
                if not variants:
                    raise RuntimeError("Producto en Tienda Nube sin variantes")
                tn_variant_id = str(variants[0]["id"])
                self.productos.actualizar_variant_id_tienda_nube(sku, tn_variant_id)

            if self.settings.dry_run:
                estado = "SIMULADO"
                detalle_tn: dict[str, Any] = {"dry_run": True}
            else:
                try:
                    detalle_tn = await self.tn.update_variant_stock(
                        product_id=tn_product_id,
                        variant_id=tn_variant_id,
                        stock=stock_nuevo,
                    )
                    self.productos.marcar_stock_sync_tienda_nube(sku)
                    estado = "ACTUALIZADO"
                except TiendaNubeHTTPError as exc:
                    if exc.status_code != 404:
                        raise
                    reparacion = await self._reparar_vinculacion_tienda_nube(
                        sku=sku,
                        tn_product_id_anterior=tn_product_id,
                        tn_variant_id_anterior=tn_variant_id,
                    )
                    if reparacion is None:
                        return {
                            "sku": sku,
                            "estado": "MAPEO_TN_OBSOLETO",
                            "stock_anterior": stock_anterior,
                            "stock_nuevo": stock_nuevo,
                            "tn_product_id": tn_product_id,
                            "tn_variant_id": tn_variant_id or None,
                        }
                    tn_product_id, tn_variant_id = reparacion
                    detalle_tn = await self.tn.update_variant_stock(
                        product_id=tn_product_id,
                        variant_id=tn_variant_id,
                        stock=stock_nuevo,
                    )
                    self.productos.marcar_stock_sync_tienda_nube(sku)
                    estado = "ACTUALIZADO_MAPEO_REPARADO"

            self.auditoria.registrar(
                sku=sku,
                accion="STOCK_SYNC_SKU",
                estado=estado,
                mensaje=f"stock_anterior={stock_anterior} stock_nuevo={stock_nuevo} dry_run={self.settings.dry_run}",
                metodo_gbp="wsExportDataById(14) -> TiendaNube.update_variant_stock",
            )
            return {
                "sku": sku,
                "estado": estado,
                "stock_anterior": stock_anterior,
                "stock_nuevo": stock_nuevo,
                "tn_product_id": tn_product_id,
                "tn_variant_id": tn_variant_id,
                "tn_response": detalle_tn,
            }
        except Exception as exc:  # noqa: BLE001 - el lote debe seguir.
            logger.exception(
                "stock_sync_sku_failed", extra={"sku": sku, "item_id": item_id}
            )
            self.db.rollback()
            try:
                self.auditoria.registrar(
                    sku=sku,
                    accion="STOCK_SYNC_SKU",
                    estado="ERROR",
                    mensaje=f"{type(exc).__name__}: {exc}",
                    metodo_gbp="wsExportDataById(14)",
                )
            except Exception:  # noqa: BLE001
                logger.exception("stock_sync_audit_failed", extra={"sku": sku})
                self.db.rollback()
            return {
                "sku": sku,
                "estado": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "stock_anterior": stock_anterior,
                "tn_product_id": tn_product_id,
                "tn_variant_id": tn_variant_id or None,
            }

    async def _reparar_vinculacion_tienda_nube(
        self,
        *,
        sku: str,
        tn_product_id_anterior: str,
        tn_variant_id_anterior: str,
    ) -> tuple[str, str] | None:
        """Autorrepara un mapeo 404 buscando el SKU vigente en Tienda Nube.

        Si el SKU ya no existe, el mapeo se marca como obsoleto para que deje de
        entrar en los lotes automáticos. Nunca crea productos desde stock.
        """

        product = await self.tn.get_product_by_sku(sku)
        if not isinstance(product, dict) or not product.get("id"):
            self.productos.marcar_mapeo_tienda_nube_obsoleto(sku)
            self.auditoria.registrar(
                sku=sku,
                accion="STOCK_SYNC_RECONCILIAR_TN",
                estado="MAPEO_TN_OBSOLETO",
                mensaje=(
                    f"product_id_anterior={tn_product_id_anterior} "
                    f"variant_id_anterior={tn_variant_id_anterior}; "
                    "el SKU ya no existe en Tienda Nube"
                ),
                metodo_gbp="TiendaNube.get_product_by_sku",
            )
            return None

        variants = product.get("variants") or []
        variant = next(
            (
                row
                for row in variants
                if str(row.get("sku") or "").strip().casefold() == sku.casefold()
            ),
            None,
        )
        if variant is None and len(variants) == 1:
            variant = variants[0]
        if not isinstance(variant, dict) or not variant.get("id"):
            self.productos.marcar_mapeo_tienda_nube_obsoleto(sku)
            self.auditoria.registrar(
                sku=sku,
                accion="STOCK_SYNC_RECONCILIAR_TN",
                estado="MAPEO_TN_OBSOLETO",
                mensaje=(
                    f"product_id_nuevo={product.get('id')} sin variante inequívoca "
                    f"para SKU={sku}"
                ),
                metodo_gbp="TiendaNube.get_product_by_sku",
            )
            return None

        nuevo_product_id = str(product["id"])
        nuevo_variant_id = str(variant["id"])
        self.productos.reparar_mapeo_tienda_nube(
            sku=sku,
            tn_product_id=nuevo_product_id,
            tn_variant_id=nuevo_variant_id,
        )
        self.auditoria.registrar(
            sku=sku,
            accion="STOCK_SYNC_RECONCILIAR_TN",
            estado="MAPEO_TN_REPARADO",
            mensaje=(
                f"product_id={tn_product_id_anterior}->{nuevo_product_id} "
                f"variant_id={tn_variant_id_anterior}->{nuevo_variant_id}"
            ),
            metodo_gbp="TiendaNube.get_product_by_sku",
        )
        return nuevo_product_id, nuevo_variant_id

    def _empty_summary(self, *, limit: int) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": self.settings.dry_run,
            "limit": limit,
            "seleccionados": 0,
            "procesados": 0,
            "actualizados": 0,
            "simulados": 0,
            "sin_cambios": 0,
            "stock_no_consultable": 0,
            "mapeos_reparados": 0,
            "mapeos_obsoletos": 0,
            "errores": 0,
            "duration_ms": 0,
            "resultados_muestra": [],
        }

    @staticmethod
    def _sumar_resultado(resumen: dict[str, Any], result: dict[str, Any]) -> None:
        resumen["procesados"] += 1
        estado = str(result.get("estado") or "")
        if estado == "ACTUALIZADO":
            resumen["actualizados"] += 1
        elif estado == "ACTUALIZADO_MAPEO_REPARADO":
            resumen["actualizados"] += 1
            resumen["mapeos_reparados"] += 1
        elif estado == "SIMULADO":
            resumen["simulados"] += 1
        elif estado == "SIN_CAMBIOS":
            resumen["sin_cambios"] += 1
        elif estado == "STOCK_NO_CONSULTABLE":
            resumen["stock_no_consultable"] += 1
        elif estado == "MAPEO_TN_OBSOLETO":
            resumen["mapeos_obsoletos"] += 1
        elif estado == "ERROR":
            resumen["errores"] += 1
