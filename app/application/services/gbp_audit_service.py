from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.application.services.producto_validation_service import ProductoValidationService
from app.infrastructure.gbp.client import GBPClient
from app.infrastructure.gbp.normalizer import GBPNormalizer
from app.infrastructure.gbp.xml_parser import any_website_image, has_value, normalizar_objeto_gbp
from app.infrastructure.persistence.repositories import ProductoRepository, SyncAuditRepository
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GBPAuditTestResult:
    """Resultado de prueba parcial de conexión y procesamiento GBP."""

    total_catalogo: int
    candidatos_con_imagen_website: int
    procesados: int
    publicables_parciales: int
    bloqueados_parciales: int
    errores: int
    resultados: list[dict[str, Any]]


class GBPAuditService:
    """Servicio de auditoría parcial GBP sin escritura en Tienda Nube."""

    def __init__(self, settings: Settings, db: Session | None = None) -> None:
        self.settings = settings
        self.db = db
        self.client = GBPClient(
            base_url=settings.gbp_base_url,
            username=settings.gbp_username,
            password=settings.gbp_password,
            timeout_seconds=settings.gbp_timeout_seconds,
            company_id=settings.gbp_company_id,
            web_service_id=settings.gbp_web_service_id,
        )
        self.normalizer = GBPNormalizer()
        self.validation_service = ProductoValidationService()

    async def ejecutar_prueba_parcial(
        self,
        *,
        limit: int = 20,
        concurrency: int = 3,
    ) -> GBPAuditTestResult:
        """Ejecuta prueba parcial Render -> GBP -> parseo -> reglas."""

        token = await self.client.autenticar()
        catalogo = await self.client.obtener_catalogo_basico(token)
        candidatos = [row for row in catalogo if any_website_image(row)]
        muestra = candidatos[:limit]

        semaphore = asyncio.Semaphore(max(1, concurrency))
        tasks = [self._procesar_candidato(semaphore, token, row) for row in muestra]
        resultados = await asyncio.gather(*tasks)

        publicables = sum(1 for row in resultados if row.get("decision") == "PUBLICABLE_PARCIAL")
        errores = sum(1 for row in resultados if row.get("error"))
        bloqueados = len(resultados) - publicables - errores

        if self.db is not None:
            SyncAuditRepository(self.db).registrar(
                sku=None,
                accion="GBP_TEST",
                estado="OK" if errores == 0 else "OK_CON_ERRORES",
                mensaje=(
                    f"total_catalogo={len(catalogo)} candidatos={len(candidatos)} "
                    f"procesados={len(resultados)} publicables_parciales={publicables} "
                    f"bloqueados={bloqueados} errores={errores}"
                ),
                metodo_gbp="ItemBasicData_funGetXMLData/wsItem_funGetXMLDataById",
            )

        return GBPAuditTestResult(
            total_catalogo=len(catalogo),
            candidatos_con_imagen_website=len(candidatos),
            procesados=len(resultados),
            publicables_parciales=publicables,
            bloqueados_parciales=bloqueados,
            errores=errores,
            resultados=resultados,
        )

    async def ejecutar_prueba_producto(
        self,
        *,
        sku: str | None = None,
        item_id: int | None = None,
        guardar_en_db: bool = True,
    ) -> dict[str, Any]:
        """Valida un producto completo con precio online y stock disponible."""

        if not sku and item_id is None:
            raise ValueError("Debe informar sku o item_id")

        token = await self.client.autenticar()
        resolved_item_id: str | int | None = item_id
        if resolved_item_id is None and sku:
            resolved_item_id = await self.client.obtener_item_id_por_codigo(token, sku)
        if resolved_item_id in (None, ""):
            raise ValueError(f"GBP no devolvió item_id para sku={sku}")

        detalle = await self.client.obtener_producto_por_id(token, int(resolved_item_id))
        imagenes = await self.client.obtener_imagenes_website_por_item_id(token, int(resolved_item_id))
        detalle = {**detalle, **self._imagenes_desde_basico(imagenes)}

        precio_rows = await self.client.obtener_precio_por_item_id(
            token,
            item_id=int(resolved_item_id),
            price_list_id=self.settings.online_price_list_id,
        )
        precio = self.normalizer.normalizar_precio(
            precio_rows,
            price_list_id=self.settings.online_price_list_id,
        )
        if precio is not None:
            detalle["precio_online"] = precio.monto
            detalle["prli_id"] = precio.lista_precio_id or str(self.settings.online_price_list_id)

        producto = self.normalizer.normalizar_producto(detalle)
        if precio is not None:
            producto.precio_importado = precio

        stock_rows = await self.client.obtener_stock_por_item_id(
            token,
            item_id=int(resolved_item_id),
            storage_id=-1,
        )
        stock_error: str | None = None
        try:
            producto.stock = self.normalizer.normalizar_stock_desde_filas(
                stock_rows,
                sku=producto.sku,
                id_sistema_gbp=producto.id_sistema_gbp,
                ecommerce_storage_ids=self.settings.ecommerce_storage_id_list,
            )
        except Exception as exc:  # noqa: BLE001 - diagnóstico controlado.
            stock_error = f"{type(exc).__name__}: {exc}"
            producto.stock = None

        resultado = self.validation_service.validar_publicacion(producto)

        if self.db is not None and guardar_en_db:
            producto_model = ProductoRepository(self.db).guardar_producto(producto)
            ProductoRepository(self.db).guardar_validacion(producto_model.id, producto, resultado)
            if producto.stock is not None:
                ProductoRepository(self.db).guardar_stock(producto_model.id, producto.stock)
            SyncAuditRepository(self.db).registrar(
                sku=producto.sku,
                accion="GBP_PRODUCT_TEST",
                estado="OK" if resultado.publicable else "BLOQUEADO",
                mensaje=(
                    f"decision={resultado.decision} motivos={','.join(resultado.motivos_bloqueo)} "
                    f"precio={'OK' if precio else 'NO'} stock={'OK' if producto.stock else 'NO'}"
                ),
                metodo_gbp="wsItem_funGetXMLDataById/PriceListItems_funGetXMLData_Short/ItemStorage_funGetXMLData",
            )

        response = {
            "ok": True,
            "dry_run": self.settings.dry_run,
            "sku": producto.sku,
            "id_sistema_gbp": producto.id_sistema_gbp,
            "titulo": producto.titulo,
            "categoria": producto.categoria_nombre,
            "subcategoria": producto.subcategoria_nombre,
            "marca": producto.marca_nombre,
            "codigo_proveedor": producto.codigo_proveedor,
            "item_web": producto.publicable_web,
            "item_disabled": producto.item_disabled,
            "item_not_for_sale": producto.item_not_for_sale,
            "tiene_imagen_website": producto.tiene_imagen_website,
            "tiene_descripcion_web": producto.tiene_descripcion_web,
            "precio_online": float(precio.monto) if precio else None,
            "precio_online_valido": producto.precio_online_valido,
            "price_list_id": self.settings.online_price_list_id,
            "stock": self._stock_response(producto.stock, stock_error),
            "decision": resultado.decision,
            "publicable": resultado.publicable,
            "motivos": resultado.motivos_bloqueo,
            "cumple": resultado.cumple,
            "precio_raw_rows": precio_rows[:3],
            "stock_raw_rows": stock_rows[:10],
        }
        return normalizar_objeto_gbp(response)

    async def _procesar_candidato(
        self,
        semaphore: asyncio.Semaphore,
        token: str,
        row: dict[str, str],
    ) -> dict[str, Any]:
        async with semaphore:
            item_id = row.get("item_id") or ""
            try:
                detalle = await self.client.obtener_producto_por_id(token, int(item_id))
                detalle = {**detalle, **self._imagenes_desde_basico(row)}
                producto = self.normalizer.normalizar_producto(detalle)
                motivos = self._motivos_bloqueo_parcial(producto)
                decision = "PUBLICABLE_PARCIAL" if not motivos else "BLOQUEADO_PARCIAL"
                return normalizar_objeto_gbp({
                    "sku": producto.sku,
                    "id_sistema_gbp": producto.id_sistema_gbp,
                    "titulo": producto.titulo,
                    "categoria": producto.categoria_nombre,
                    "subcategoria": producto.subcategoria_nombre,
                    "marca": producto.marca_nombre,
                    "codigo_proveedor": producto.codigo_proveedor,
                    "item_web": producto.publicable_web,
                    "item_disabled": producto.item_disabled,
                    "item_not_for_sale": producto.item_not_for_sale,
                    "tiene_imagen_website": producto.tiene_imagen_website,
                    "tiene_descripcion_web": producto.tiene_descripcion_web,
                    "decision": decision,
                    "motivos": motivos,
                })
            except Exception as exc:  # noqa: BLE001 - respuesta controlada de diagnóstico.
                logger.exception("gbp_test_item_error", extra={"item_id": item_id})
                return normalizar_objeto_gbp({
                    "sku": row.get("item_code"),
                    "id_sistema_gbp": item_id,
                    "titulo": row.get("item_desc"),
                    "decision": "ERROR_CONSULTA_DETALLE",
                    "motivos": ["ERROR_GBP"],
                    "error": f"{type(exc).__name__}: {exc}",
                })

    @staticmethod
    def _imagenes_desde_basico(row: dict[str, str]) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for index in range(1, 11):
            for prefix in ("item_WebSite_url4Image", "item_WebSite_url4image"):
                value = row.get(f"{prefix}{index}")
                if has_value(value):
                    mapped[f"item_WebSite_url4Image{index}"] = str(value)
                    break
        return mapped

    @staticmethod
    def _motivos_bloqueo_parcial(producto: Any) -> list[str]:
        motivos: list[str] = []
        if not producto.sku.strip():
            motivos.append("SIN_SKU")
        if not producto.titulo.strip():
            motivos.append("SIN_TITULO")
        if not producto.tiene_imagen_website:
            motivos.append("SIN_IMAGEN_WEBSITE")
        if producto.publicable_web is not True:
            motivos.append("ITEM_WEB_NO_VALIDO")
        if producto.item_disabled:
            motivos.append("ITEM_DISABLED")
        if producto.item_not_for_sale:
            motivos.append("ITEM_NOT_FOR_SALE")
        if not producto.tiene_descripcion_web:
            motivos.append("SIN_DESCRIPCION_WEB")
        return motivos

    @staticmethod
    def _stock_response(stock: Any, error: str | None) -> dict[str, Any]:
        if stock is None:
            return {
                "consultable": False,
                "error": error,
                "cantidad_tn": None,
                "stock_original_gbp": None,
                "depositos": [],
            }
        return {
            "consultable": stock.consultable,
            "cantidad_tn": stock.cantidad,
            "stock_original_gbp": stock.stock_original_gbp,
            "depositos": [deposito.model_dump() for deposito in stock.depositos],
        }
