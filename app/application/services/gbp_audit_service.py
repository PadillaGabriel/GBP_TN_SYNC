from __future__ import annotations

import asyncio
import logging
import time
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


    async def ejecutar_auditoria_productos(
        self,
        *,
        limit: int | None = None,
        concurrency: int = 3,
        guardar_en_db: bool = True,
    ) -> dict[str, Any]:
        """Ejecuta auditoría real masiva GBP -> Railway con tolerancia a fallos.

        No crea productos en Tienda Nube. No actualiza stock en Tienda Nube.
        Si un producto o una escritura de DB falla, el proceso conserva el
        resumen parcial y devuelve JSON en lugar de cortar con HTTP 500.
        """

        started = time.perf_counter()
        resumen: dict[str, Any] = {
            "ok": False,
            "dry_run": self.settings.dry_run,
            "total_catalogo": 0,
            "candidatos_con_imagen_website": 0,
            "procesados": 0,
            "publicables": 0,
            "bloqueados": 0,
            "errores": 0,
            "errores_persistencia": 0,
            "decisiones": {},
            "online_price_list_id": self.settings.online_price_list_id,
            "ecommerce_storage_ids": self.settings.ecommerce_storage_id_list,
            "duration_ms": 0,
            "resultados_muestra": [],
            "error_global": None,
        }

        try:
            token = await self.client.autenticar()
            catalogo = await self.client.obtener_catalogo_basico(token)
            candidatos = [row for row in catalogo if any_website_image(row)]
            seleccionados = candidatos[:limit] if limit else candidatos

            resumen["total_catalogo"] = len(catalogo)
            resumen["candidatos_con_imagen_website"] = len(candidatos)

            semaphore = asyncio.Semaphore(max(1, concurrency))
            tasks = [
                self._procesar_candidato_completo(semaphore, token, row)
                for row in seleccionados
            ]
            resultados = await asyncio.gather(*tasks, return_exceptions=True)

            resultados_validos: list[dict[str, Any]] = []
            for item in resultados:
                if isinstance(item, Exception):
                    logger.exception("gbp_audit_unhandled_task_error", exc_info=item)
                    row = {
                        "decision": "ERROR_VALIDACION",
                        "publicable": False,
                        "motivos": ["ERROR_NO_CONTROLADO"],
                        "error": f"{type(item).__name__}: {item}",
                    }
                else:
                    row = item
                resultados_validos.append(row)

            for row in resultados_validos:
                resumen["procesados"] += 1
                decision = str(row.get("decision") or "ERROR_VALIDACION")
                decisiones = resumen["decisiones"]
                decisiones[decision] = decisiones.get(decision, 0) + 1

                if row.get("error"):
                    resumen["errores"] += 1
                elif decision == "PUBLICABLE_AUTOMATICO":
                    resumen["publicables"] += 1
                else:
                    resumen["bloqueados"] += 1

            if self.db is not None and guardar_en_db:
                self._persistir_resultados_auditoria(resultados_validos, resumen)

            duration_ms = int((time.perf_counter() - started) * 1000)
            resumen["duration_ms"] = duration_ms
            resumen["ok"] = resumen["errores"] == 0 and resumen["errores_persistencia"] == 0
            resumen["resultados_muestra"] = [
                self._resultado_publico(row) for row in resultados_validos[:20]
            ]

            if self.db is not None and guardar_en_db:
                self._registrar_resumen_auditoria(resumen)

            return normalizar_objeto_gbp(resumen)

        except Exception as exc:  # noqa: BLE001 - se devuelve resumen parcial.
            logger.exception("gbp_audit_global_error")
            resumen["ok"] = False
            resumen["error_global"] = f"{type(exc).__name__}: {exc}"
            resumen["duration_ms"] = int((time.perf_counter() - started) * 1000)
            if self.db is not None and guardar_en_db:
                try:
                    SyncAuditRepository(self.db).registrar(
                        sku=None,
                        accion="GBP_AUDIT_PRODUCTS_RUN",
                        estado="ERROR_GLOBAL",
                        mensaje=str(resumen["error_global"]),
                        metodo_gbp=(
                            "ItemBasicData_funGetXMLData/wsItem_funGetXMLDataById/"
                            "PriceListItems_funGetXMLData_Short/ItemStorage_funGetXMLData"
                        ),
                        duracion_ms=resumen["duration_ms"],
                    )
                except Exception:  # noqa: BLE001 - no romper respuesta al operador.
                    logger.exception("gbp_audit_global_error_audit_log_failed")
                    self.db.rollback()
            return normalizar_objeto_gbp(resumen)

    def _persistir_resultados_auditoria(
        self,
        resultados: list[dict[str, Any]],
        resumen: dict[str, Any],
    ) -> None:
        """Guarda resultados de auditoría sin cortar el proceso por una fila."""

        productos_repo = ProductoRepository(self.db)  # type: ignore[arg-type]
        audit_repo = SyncAuditRepository(self.db)  # type: ignore[arg-type]

        for row in resultados:
            if row.get("error"):
                try:
                    audit_repo.registrar(
                        sku=row.get("sku"),
                        accion="GBP_AUDIT_PRODUCT_ERROR",
                        estado="ERROR",
                        mensaje=str(row.get("error")),
                        metodo_gbp=(
                            "wsItem_funGetXMLDataById/PriceListItems_funGetXMLData_Short/"
                            "ItemStorage_funGetXMLData"
                        ),
                    )
                except Exception:  # noqa: BLE001 - registrar el fallo y seguir.
                    resumen["errores_persistencia"] += 1
                    logger.exception("gbp_audit_error_row_persist_failed")
                    self.db.rollback()  # type: ignore[union-attr]
                continue

            try:
                producto = row["producto"]
                resultado = row["resultado"]
                producto_model = productos_repo.guardar_producto(producto)
                productos_repo.guardar_validacion(producto_model.id, producto, resultado)
                if producto.stock is not None:
                    productos_repo.guardar_stock(producto_model.id, producto.stock)
            except Exception:  # noqa: BLE001 - una fila no debe tirar el endpoint.
                resumen["errores_persistencia"] += 1
                logger.exception(
                    "gbp_audit_product_persist_failed",
                    extra={"sku": row.get("sku"), "item_id": row.get("id_sistema_gbp")},
                )
                self.db.rollback()  # type: ignore[union-attr]

    def _registrar_resumen_auditoria(self, resumen: dict[str, Any]) -> None:
        """Registra evento final de auditoría sin romper la respuesta."""

        try:
            estado = "OK" if resumen["ok"] else "OK_CON_ERRORES"
            SyncAuditRepository(self.db).registrar(  # type: ignore[arg-type]
                sku=None,
                accion="GBP_AUDIT_PRODUCTS_RUN",
                estado=estado,
                mensaje=(
                    f"total_catalogo={resumen['total_catalogo']} "
                    f"candidatos={resumen['candidatos_con_imagen_website']} "
                    f"procesados={resumen['procesados']} "
                    f"publicables={resumen['publicables']} "
                    f"bloqueados={resumen['bloqueados']} "
                    f"errores={resumen['errores']} "
                    f"errores_persistencia={resumen['errores_persistencia']} "
                    f"decisiones={resumen['decisiones']}"
                ),
                metodo_gbp=(
                    "ItemBasicData_funGetXMLData/wsItem_funGetXMLDataById/"
                    "PriceListItems_funGetXMLData_Short/ItemStorage_funGetXMLData"
                ),
                duracion_ms=int(resumen["duration_ms"]),
            )
        except Exception:  # noqa: BLE001 - no romper la respuesta por auditoría final.
            logger.exception("gbp_audit_summary_persist_failed")
            self.db.rollback()  # type: ignore[union-attr]

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


    async def _procesar_candidato_completo(
        self,
        semaphore: asyncio.Semaphore,
        token: str,
        row: dict[str, str],
    ) -> dict[str, Any]:
        async with semaphore:
            item_id = row.get("item_id") or ""
            sku = row.get("item_code")
            try:
                detalle = await self.client.obtener_producto_por_id(token, int(item_id))
                detalle = {**detalle, **self._imagenes_desde_basico(row)}

                precio_rows = await self.client.obtener_precio_por_item_id(
                    token,
                    item_id=int(item_id),
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
                    item_id=int(item_id),
                    storage_id=-1,
                )
                try:
                    producto.stock = self.normalizer.normalizar_stock_desde_filas(
                        stock_rows,
                        sku=producto.sku,
                        id_sistema_gbp=producto.id_sistema_gbp,
                        ecommerce_storage_ids=self.settings.ecommerce_storage_id_list,
                    )
                except Exception:  # noqa: BLE001 - validación debe marcar falta de stock.
                    producto.stock = None

                resultado = self.validation_service.validar_publicacion(producto)
                return {
                    "sku": producto.sku,
                    "id_sistema_gbp": producto.id_sistema_gbp,
                    "titulo": producto.titulo,
                    "decision": resultado.decision,
                    "publicable": resultado.publicable,
                    "motivos": resultado.motivos_bloqueo,
                    "precio_online": float(precio.monto) if precio else None,
                    "stock_tn": producto.stock.cantidad if producto.stock else None,
                    "producto": producto,
                    "resultado": resultado,
                }
            except Exception as exc:  # noqa: BLE001 - se conserva error por producto.
                logger.exception("gbp_audit_product_error", extra={"item_id": item_id, "sku": sku})
                return normalizar_objeto_gbp({
                    "sku": sku,
                    "id_sistema_gbp": item_id,
                    "titulo": row.get("item_desc"),
                    "decision": "ERROR_VALIDACION",
                    "publicable": False,
                    "motivos": ["ERROR_GBP"],
                    "error": f"{type(exc).__name__}: {exc}",
                })

    @staticmethod
    def _resultado_publico(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "sku": row.get("sku"),
            "id_sistema_gbp": row.get("id_sistema_gbp"),
            "titulo": row.get("titulo"),
            "decision": row.get("decision"),
            "publicable": row.get("publicable"),
            "motivos": row.get("motivos", []),
            "precio_online": row.get("precio_online"),
            "stock_tn": row.get("stock_tn"),
            "error": row.get("error"),
        }

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
