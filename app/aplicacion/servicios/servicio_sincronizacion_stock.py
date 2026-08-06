from __future__ import annotations

import logging
import time
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

    async def sincronizar_lote(self, *, limit: int = 100) -> dict[str, Any]:
        """Sincroniza stock de los primeros mapeos activos disponibles."""

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
        for item in items:
            result = await self._sincronizar_item(
                item, fila_stock=por_item.get(str(item["id_sistema_gbp"]))
            )
            resultados.append(result)
            self._sumar_resultado(resumen, result)

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
        result["ok"] = result.get("estado") not in {"ERROR", "STOCK_NO_CONSULTABLE"}
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
                detalle_tn = await self.tn.update_variant_stock(
                    product_id=tn_product_id,
                    variant_id=tn_variant_id,
                    stock=stock_nuevo,
                )
                self.productos.marcar_stock_sync_tienda_nube(sku)
                estado = "ACTUALIZADO"

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
        elif estado == "SIMULADO":
            resumen["simulados"] += 1
        elif estado == "SIN_CAMBIOS":
            resumen["sin_cambios"] += 1
        elif estado == "STOCK_NO_CONSULTABLE":
            resumen["stock_no_consultable"] += 1
        elif estado == "ERROR":
            resumen["errores"] += 1
