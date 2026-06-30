from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.application.services.producto_validation_service import ProductoValidationService
from app.domain.errors import DatoIncompletoError, GBPProductoNoConsultableError, GBPSkuNoResueltoError
from app.domain.models.producto import Producto
from app.infrastructure.gbp.client import GBPClient
from app.infrastructure.gbp.normalizer import GBPNormalizer
from app.infrastructure.gbp.xml_parser import normalizar_objeto_gbp
from app.infrastructure.persistence.repositories import ProductoRepository, SyncAuditRepository
from app.infrastructure.tienda_nube.adapter import TiendaNubeAdapter
from app.infrastructure.tienda_nube.client import TiendaNubeClient
from app.infrastructure.tienda_nube.payload_builder import TiendaNubePayloadBuilder
from app.settings import Settings

logger = logging.getLogger(__name__)


class TiendaNubeImportService:
    """Servicio de importación controlada desde GBP hacia Tienda Nube."""

    def __init__(self, settings: Settings, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.gbp_client = GBPClient(
            base_url=settings.gbp_base_url,
            username=settings.gbp_username,
            password=settings.gbp_password,
            timeout_seconds=settings.gbp_timeout_seconds,
            company_id=settings.gbp_company_id,
            web_service_id=settings.gbp_web_service_id,
        )
        self.normalizer = GBPNormalizer()
        self.validation_service = ProductoValidationService()
        self.productos_repo = ProductoRepository(db)
        self.audit_repo = SyncAuditRepository(db)
        self.payload_builder = TiendaNubePayloadBuilder()

    async def importar_prueba_tienda_nube(
        self,
        *,
        limit: int = 20,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Importa una muestra controlada de productos publicables.

        Reglas de seguridad:
        - Si DRY_RUN=true, no escribe en Tienda Nube aunque confirm=True.
        - Si confirm=False, no escribe en Tienda Nube aunque DRY_RUN=false.
        - Solo procesa productos con decisión PUBLICABLE_AUTOMATICO ya guardados.
        """

        started = time.perf_counter()
        ejecutar_tn = bool(confirm and not self.settings.dry_run)
        resumen: dict[str, Any] = {
            "ok": True,
            "dry_run": self.settings.dry_run,
            "confirm": confirm,
            "ejecuta_tienda_nube": ejecutar_tn,
            "limit": limit,
            "seleccionados": 0,
            "procesados": 0,
            "creados": 0,
            "actualizados": 0,
            "simulados": 0,
            "bloqueados": 0,
            "errores": 0,
            "resultados": [],
            "duration_ms": None,
        }

        productos_base = self.productos_repo.listar_publicables_para_importar(limit=limit)
        resumen["seleccionados"] = len(productos_base)

        token = await self.gbp_client.autenticar()
        tn_adapter = self._crear_tienda_nube_adapter()

        for base in productos_base:
            sku = str(base["sku"])
            item_id = str(base["id_sistema_gbp"])
            try:
                producto = await self._obtener_producto_publicable(token=token, item_id=item_id)
                validacion = self.validation_service.validar_publicacion(producto)
                self._persistir_producto_validado(producto, validacion)
                if not validacion.publicable:
                    resumen["bloqueados"] += 1
                    resumen["resultados"].append(
                        {
                            "sku": sku,
                            "id_sistema_gbp": item_id,
                            "estado": "BLOQUEADO",
                            "decision": validacion.decision,
                            "motivos": validacion.motivos_bloqueo,
                        }
                    )
                    continue

                payload = self.payload_builder.build_product_payload(producto)
                if not ejecutar_tn:
                    resumen["simulados"] += 1
                    resumen["procesados"] += 1
                    resumen["resultados"].append(
                        {
                            "sku": producto.sku,
                            "id_sistema_gbp": producto.id_sistema_gbp,
                            "titulo": producto.titulo,
                            "estado": "DRY_RUN" if self.settings.dry_run else "SIMULADO_SIN_CONFIRMACION",
                            "accion": "crear_o_actualizar_producto",
                            "precio": str(producto.precio_importado.monto) if producto.precio_importado else None,
                            "stock": producto.stock.cantidad if producto.stock else None,
                            "imagenes": len(producto.imagenes),
                            "payload_preview": payload,
                            "categoria": producto.categoria_nombre,
                            "subcategoria": producto.subcategoria_nombre,
                            "descripcion_largo": len(producto.descripcion_web or ""),
                            "descripcion_preview": (producto.descripcion_web or "")[:300],
                        }
                    )
                    continue

                resultado = await tn_adapter.crear_o_actualizar_producto(producto)
                resumen["procesados"] += 1
                accion = resultado.accion
                if accion == "crear_producto":
                    resumen["creados"] += 1
                elif accion == "actualizar_producto":
                    resumen["actualizados"] += 1

                tn_product = resultado.detalles.get("tn_product", {}) if resultado.detalles else {}
                tn_product_id = self._extraer_tn_product_id(tn_product)
                tn_variant_id = self._extraer_tn_variant_id(tn_product)
                if tn_product_id:
                    producto_model = self.productos_repo.obtener_por_sku(producto.sku)
                    if producto_model is not None:
                        self.productos_repo.guardar_mapeo_tienda_nube(
                            producto_fuente_id=producto_model.id,
                            sku=producto.sku,
                            tn_product_id=tn_product_id,
                            tn_variant_id=tn_variant_id,
                            estado_publicacion="activo",
                        )

                self.audit_repo.registrar(
                    sku=producto.sku,
                    accion="TN_IMPORT_PRODUCT_TEST",
                    estado="OK",
                    mensaje=f"accion={accion} tn_product_id={tn_product_id or ''}",
                    metodo_gbp="TiendaNubeAdapter.crear_o_actualizar_producto",
                )
                resumen["resultados"].append(
                    {
                        "sku": producto.sku,
                        "id_sistema_gbp": producto.id_sistema_gbp,
                        "titulo": producto.titulo,
                        "estado": "OK",
                        "accion": accion,
                        "tn_product_id": tn_product_id,
                        "tn_variant_id": tn_variant_id,
                        "precio": str(producto.precio_importado.monto) if producto.precio_importado else None,
                        "stock": producto.stock.cantidad if producto.stock else None,
                        "imagenes": len(producto.imagenes),
                        "categoria": producto.categoria_nombre,
                        "subcategoria": producto.subcategoria_nombre,
                        "descripcion_largo": len(producto.descripcion_web or ""),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - una fila no debe cortar el lote.
                logger.exception("tn_import_product_failed", extra={"sku": sku, "item_id": item_id})
                self.db.rollback()
                resumen["errores"] += 1
                resumen["resultados"].append(
                    {
                        "sku": sku,
                        "id_sistema_gbp": item_id,
                        "estado": "ERROR",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        resumen["duration_ms"] = int((time.perf_counter() - started) * 1000)
        resumen["ok"] = resumen["errores"] == 0
        self._registrar_resumen(resumen)
        return normalizar_objeto_gbp(resumen)


    async def importar_producto_manual_tienda_nube(
        self,
        *,
        sku: str | None = None,
        item_id: int | None = None,
        confirm: bool = False,
        forzar: bool = False,
    ) -> dict[str, Any]:
        """Importa o actualiza un producto puntual bajo control manual.

        - Si DRY_RUN=true, no escribe en Tienda Nube.
        - Si confirm=False, no escribe en Tienda Nube.
        - Si el producto queda bloqueado, solo escribe si forzar=True.
        """

        if not sku and item_id is None:
            raise ValueError("Debe informar sku o item_id")

        started = time.perf_counter()
        ejecutar_tn = bool(confirm and not self.settings.dry_run)
        token = await self.gbp_client.autenticar()
        resolved_item_id: str | int | None = item_id
        if resolved_item_id is None and sku:
            resolved_item_id = await self.gbp_client.obtener_item_id_por_codigo(token, sku)
        if resolved_item_id in (None, ""):
            return normalizar_objeto_gbp(
                {
                    "ok": True,
                    "dry_run": self.settings.dry_run,
                    "confirm": confirm,
                    "forzar": forzar,
                    "ejecuta_tienda_nube": False,
                    "sku": sku,
                    "id_sistema_gbp": None,
                    "estado": "BLOQUEADO",
                    "decision": "NO_PUBLICAR_SKU_NO_RESUELTO",
                    "motivos": ["SKU_NO_RESUELTO"],
                    "mensaje": f"GBP no devolvió item_id para sku={sku}",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        producto = await self._obtener_producto_manual_flexible(
            token=token,
            item_id=str(resolved_item_id),
            sku=sku or str(resolved_item_id),
        )

        validacion = self.validation_service.validar_publicacion(
            producto,
            exigir_item_web=False,
            modo_manual_flexible=True,
        )
        self._persistir_producto_validado(producto, validacion)

        payload = self.payload_builder.build_product_payload(producto)
        bloqueado = not validacion.publicable
        if bloqueado and not forzar:
            return normalizar_objeto_gbp(
                {
                    "ok": True,
                    "dry_run": self.settings.dry_run,
                    "confirm": confirm,
                    "forzar": forzar,
                    "ejecuta_tienda_nube": False,
                    "sku": producto.sku,
                    "id_sistema_gbp": producto.id_sistema_gbp,
                    "titulo": producto.titulo,
                    "estado": "BLOQUEADO",
                    "decision": validacion.decision,
                    "motivos": validacion.motivos_bloqueo,
                    "precio": str(producto.precio_importado.monto) if producto.precio_importado else None,
                    "stock": producto.stock.cantidad if producto.stock else None,
                    "payload_preview": payload,
                    "descripcion_largo": len(producto.descripcion_web or ""),
                    "descripcion_preview": (producto.descripcion_web or "")[:300],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        if not ejecutar_tn:
            return normalizar_objeto_gbp(
                {
                    "ok": True,
                    "dry_run": self.settings.dry_run,
                    "confirm": confirm,
                    "forzar": forzar,
                    "ejecuta_tienda_nube": False,
                    "sku": producto.sku,
                    "id_sistema_gbp": producto.id_sistema_gbp,
                    "titulo": producto.titulo,
                    "estado": "DRY_RUN" if self.settings.dry_run else "SIMULADO_SIN_CONFIRMACION",
                    "decision": validacion.decision,
                    "motivos": validacion.motivos_bloqueo,
                    "accion": "crear_o_actualizar_producto_manual",
                    "precio": str(producto.precio_importado.monto) if producto.precio_importado else None,
                    "stock": producto.stock.cantidad if producto.stock else None,
                    "payload_preview": payload,
                    "descripcion_largo": len(producto.descripcion_web or ""),
                    "descripcion_preview": (producto.descripcion_web or "")[:300],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        tn_adapter = self._crear_tienda_nube_adapter()
        resultado = await tn_adapter.crear_o_actualizar_producto(producto)
        tn_product = resultado.detalles.get("tn_product", {}) if resultado.detalles else {}
        tn_product_id = self._extraer_tn_product_id(tn_product)
        tn_variant_id = self._extraer_tn_variant_id(tn_product)
        if tn_product_id:
            producto_model = self.productos_repo.obtener_por_sku(producto.sku)
            if producto_model is not None:
                self.productos_repo.guardar_mapeo_tienda_nube(
                    producto_fuente_id=producto_model.id,
                    sku=producto.sku,
                    tn_product_id=tn_product_id,
                    tn_variant_id=tn_variant_id,
                    estado_publicacion="activo_manual" if bloqueado else "activo",
                )

        self.audit_repo.registrar(
            sku=producto.sku,
            accion="TN_IMPORT_PRODUCT_MANUAL",
            estado="OK",
            mensaje=(
                f"accion={resultado.accion} tn_product_id={tn_product_id or ''} "
                f"forzar={forzar} decision={validacion.decision}"
            ),
            metodo_gbp="TiendaNubeAdapter.crear_o_actualizar_producto",
            duracion_ms=int((time.perf_counter() - started) * 1000),
        )
        return normalizar_objeto_gbp(
            {
                "ok": True,
                "dry_run": self.settings.dry_run,
                "confirm": confirm,
                "forzar": forzar,
                "ejecuta_tienda_nube": True,
                "sku": producto.sku,
                "id_sistema_gbp": producto.id_sistema_gbp,
                "titulo": producto.titulo,
                "estado": "OK",
                "decision": validacion.decision,
                "motivos": validacion.motivos_bloqueo,
                "accion": resultado.accion,
                "tn_product_id": tn_product_id,
                "tn_variant_id": tn_variant_id,
                "precio": str(producto.precio_importado.monto) if producto.precio_importado else None,
                "stock": producto.stock.cantidad if producto.stock else None,
                "descripcion_largo": len(producto.descripcion_web or ""),
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )

    async def ocultar_producto_tienda_nube(
        self,
        *,
        sku: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Oculta/despublica un producto ya mapeado en Tienda Nube.

        Con DRY_RUN=true o confirm=False no escribe en Tienda Nube.
        No borra el mapeo local: cambia estado_publicacion para auditoría.
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
                    "accion": "ocultar_tienda_nube",
                    "estado": "DRY_RUN" if self.settings.dry_run else "SIMULADO_SIN_CONFIRMACION",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        client = self._crear_tienda_nube_adapter().client
        result = await client.hide_product(mapeo.tn_product_id)
        self.productos_repo.actualizar_estado_mapeo_tienda_nube(sku, "oculto_tn")
        self.audit_repo.registrar(
            sku=sku,
            accion="TN_HIDE_PRODUCT_MANUAL",
            estado="OK",
            mensaje=f"tn_product_id={mapeo.tn_product_id}",
            metodo_gbp="TiendaNubeClient.hide_product",
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
                "accion": "ocultar_tienda_nube",
                "estado": "OK",
                "resultado_tienda_nube": result,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )

    async def eliminar_producto_tienda_nube(
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
                    "estado": "DRY_RUN" if self.settings.dry_run else "SIMULADO_SIN_CONFIRMACION",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        client = self._crear_tienda_nube_adapter().client
        result = await client.delete_product(mapeo.tn_product_id)
        self.productos_repo.actualizar_estado_mapeo_tienda_nube(sku, "eliminado_tn")
        self.audit_repo.registrar(
            sku=sku,
            accion="TN_DELETE_PRODUCT_MANUAL",
            estado="OK",
            mensaje=f"tn_product_id={mapeo.tn_product_id}",
            metodo_gbp="TiendaNubeClient.delete_product",
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

    async def reconciliar_mapeos_tienda_nube(
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
        client = self._crear_tienda_nube_adapter().client
        mapeos = self.productos_repo.listar_mapeos_tienda_nube(limit=limit, offset=offset)
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
                    self.productos_repo.actualizar_estado_mapeo_tienda_nube(mapeo.sku, "eliminado_externo")
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
                logger.exception("tn_reconcile_mapping_failed", extra={"sku": mapeo.sku})
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
            metodo_gbp="TiendaNubeClient.get_product",
            duracion_ms=int(resumen["duration_ms"] or 0),
        )
        return normalizar_objeto_gbp(resumen)

    def marcar_mapeos_como_eliminados_externos(
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
            metodo_gbp="ProductoRepository.marcar_todos_mapeos_como_eliminados_externos",
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

    async def _obtener_producto_publicable(self, *, token: str, item_id: str):
        detalle = await self.gbp_client.obtener_producto_por_id_robusto(token, int(item_id))
        imagenes = await self.gbp_client.obtener_imagenes_website_por_item_id(token, int(item_id))
        detalle = {**detalle, **self._imagenes_desde_website(imagenes)}

        precio_rows = await self.gbp_client.obtener_precio_por_item_id(
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

        stock_rows = await self.gbp_client.obtener_stock_por_item_id(
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
        except Exception:  # noqa: BLE001 - validacion debe marcar stock no consultable.
            logger.exception("tn_import_stock_normalization_failed", extra={"item_id": item_id})
            producto.stock = None
        return producto


    async def _obtener_producto_manual_flexible(
        self,
        *,
        token: str,
        item_id: str,
        sku: str,
    ) -> Producto:
        """
        Obtiene un producto para importación manual.

        Si GBP no devuelve ficha completa o el normalizador no puede armar el
        producto completo, se construye un Producto mínimo para permitir carga
        manual con precio 0, stock 0 y descripción básica.
        """

        try:
            return await self._obtener_producto_publicable(token=token, item_id=item_id)
        except (GBPProductoNoConsultableError, DatoIncompletoError) as exc:
            logger.warning(
                "tn_import_producto_minimo_manual",
                extra={
                    "sku": sku,
                    "item_id": str(item_id),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return self._crear_producto_minimo_manual(
                sku=sku,
                item_id=str(item_id),
                titulo=sku,
            )

    def _crear_producto_minimo_manual(
        self,
        *,
        sku: str,
        item_id: str,
        titulo: str | None = None,
    ) -> Producto:
        """
        Crea un Producto mínimo para publicación manual flexible.

        Este fallback no se usa en auditoría ni importación masiva. El payload
        resultante se genera con precio 0.00 y stock 0 para evitar ventas
        accidentales hasta que se complete manualmente en Tienda Nube.
        """

        sku_final = str(sku or item_id).strip()
        titulo_final = str(titulo or sku_final or f"Producto {item_id}").strip()

        return Producto(
            sku=sku_final,
            id_sistema_gbp=str(item_id).strip(),
            titulo=titulo_final,
            publicable_web=None,
            item_disabled=False,
            item_not_for_sale=False,
            descripcion_web=titulo_final,
            imagenes=[],
            precio_importado=None,
            stock=None,
        )

    def _persistir_producto_validado(self, producto, validacion) -> None:
        """Persiste producto, validacion y stock sin duplicar lógica."""

        producto_model = self.productos_repo.guardar_producto(producto)
        self.productos_repo.guardar_validacion(producto_model.id, producto, validacion)
        if producto.stock is not None:
            self.productos_repo.guardar_stock(producto_model.id, producto.stock)

    def _crear_tienda_nube_adapter(self) -> TiendaNubeAdapter:
        client = TiendaNubeClient(
            base_url=self.settings.tienda_nube_base_url,
            store_id=self.settings.tienda_nube_store_id,
            access_token=self.settings.tienda_nube_access_token,
            timeout_seconds=self.settings.tienda_nube_timeout_seconds,
        )
        return TiendaNubeAdapter(
            client=client,
            image_normalization_enabled=self.settings.image_normalization_enabled,
            image_normalization_base_url=self.settings.app_public_base_url,
            image_normalization_canvas_size=self.settings.image_normalization_canvas_size,
        )

    @staticmethod
    def _imagenes_desde_website(row: dict[str, str]) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for index in range(1, 11):
            value = row.get(f"item_WebSite_url4Image{index}")
            if value:
                mapped[f"item_WebSite_url4Image{index}"] = value
        return mapped

    @staticmethod
    def _extraer_tn_product_id(tn_product: object) -> str | None:
        if isinstance(tn_product, dict):
            value = tn_product.get("id")
            return str(value) if value not in (None, "") else None
        return None

    @staticmethod
    def _extraer_tn_variant_id(tn_product: object) -> str | None:
        if not isinstance(tn_product, dict):
            return None
        variants = tn_product.get("variants") or []
        if not variants or not isinstance(variants, list):
            return None
        first = variants[0]
        if not isinstance(first, dict):
            return None
        value = first.get("id")
        return str(value) if value not in (None, "") else None

    def _registrar_resumen(self, resumen: dict[str, Any]) -> None:
        try:
            self.audit_repo.registrar(
                sku=None,
                accion="TN_IMPORT_TEST_RUN",
                estado="OK" if resumen["ok"] else "OK_CON_ERRORES",
                mensaje=(
                    f"seleccionados={resumen['seleccionados']} procesados={resumen['procesados']} "
                    f"creados={resumen['creados']} actualizados={resumen['actualizados']} "
                    f"simulados={resumen['simulados']} bloqueados={resumen['bloqueados']} "
                    f"errores={resumen['errores']} ejecuta_tn={resumen['ejecuta_tienda_nube']}"
                ),
                metodo_gbp="GBP->TiendaNube importar_prueba_tienda_nube",
                duracion_ms=int(resumen["duration_ms"] or 0),
            )
        except Exception:  # noqa: BLE001 - no romper respuesta por auditoría.
            logger.exception("tn_import_test_summary_persist_failed")
            self.db.rollback()
