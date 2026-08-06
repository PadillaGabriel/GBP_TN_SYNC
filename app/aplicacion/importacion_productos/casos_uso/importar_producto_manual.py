from __future__ import annotations

import logging
import time
from typing import Any

from app.infraestructura.gbp.analizador_xml import normalizar_objeto_gbp
from app.aplicacion.importacion_productos.utilidades_tienda_nube import (
    extraer_id_producto_tn,
    extraer_id_variante_tn,
)

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


class ImportarProductoManual(OperacionImportacionBase):
    async def ejecutar(
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
            resolved_item_id = await self.gbp_client.obtener_item_id_por_codigo(
                token, sku
            )
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

        producto = await self.resolvedor_producto.obtener_manual_flexible(
            token=token,
            item_id=str(resolved_item_id),
            sku=sku or str(resolved_item_id),
        )
        producto = await self.resolvedor_producto.enriquecer_manual(
            producto,
            token=token,
            item_id=str(resolved_item_id),
        )

        validacion = self.validation_service.validar_publicacion(
            producto,
            exigir_item_web=False,
            modo_manual_flexible=True,
        )
        self.persistidor_producto.guardar(producto, validacion)

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
                    "precio": str(producto.precio_importado.monto)
                    if producto.precio_importado
                    else None,
                    "stock": producto.stock.cantidad if producto.stock else None,
                    "imagenes": len(producto.imagenes),
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
                    "estado": "DRY_RUN"
                    if self.settings.dry_run
                    else "SIMULADO_SIN_CONFIRMACION",
                    "decision": validacion.decision,
                    "motivos": validacion.motivos_bloqueo,
                    "accion": "crear_o_actualizar_producto_manual",
                    "precio": str(producto.precio_importado.monto)
                    if producto.precio_importado
                    else None,
                    "stock": producto.stock.cantidad if producto.stock else None,
                    "imagenes": len(producto.imagenes),
                    "payload_preview": payload,
                    "descripcion_largo": len(producto.descripcion_web or ""),
                    "descripcion_preview": (producto.descripcion_web or "")[:300],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )

        tn_adapter = self.fabrica_tienda_nube.crear()
        resultado = await tn_adapter.crear_o_actualizar_producto(producto)
        tn_product = (
            resultado.detalles.get("tn_product", {}) if resultado.detalles else {}
        )
        tn_product_id = extraer_id_producto_tn(tn_product)
        tn_variant_id = extraer_id_variante_tn(tn_product)
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
            metodo_gbp="AdaptadorTiendaNube.crear_o_actualizar_producto",
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
                "precio": str(producto.precio_importado.monto)
                if producto.precio_importado
                else None,
                "stock": producto.stock.cantidad if producto.stock else None,
                "imagenes": len(producto.imagenes),
                "descripcion_largo": len(producto.descripcion_web or ""),
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )
