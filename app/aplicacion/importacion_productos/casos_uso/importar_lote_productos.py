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


class ImportarLoteProductos(OperacionImportacionBase):
    async def ejecutar(
        self,
        *,
        limit: int = 20,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Importa una muestra controlada de productos publicables.

        Reglas de seguridad:
        - Si DRY_RUN=true, no escribe en Tienda Nube aunque confirm=True.
        - Si confirm=False, no escribe en Tienda Nube aunque DRY_RUN=false.
        - Solo procesa productos con una decisión publicable ya guardada y revalida antes de escribir.
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

        productos_base = self.productos_repo.listar_publicables_para_importar(
            limit=limit
        )
        resumen["seleccionados"] = len(productos_base)

        token = await self.gbp_client.autenticar()
        tn_adapter = self.fabrica_tienda_nube.crear()

        for base in productos_base:
            sku = str(base["sku"])
            item_id = str(base["id_sistema_gbp"])
            try:
                producto = await self.resolvedor_producto.obtener_publicable(
                    token=token, item_id=item_id
                )
                validacion = self.validation_service.validar_publicacion(producto)
                self.persistidor_producto.guardar(producto, validacion)
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
                            "estado": "DRY_RUN"
                            if self.settings.dry_run
                            else "SIMULADO_SIN_CONFIRMACION",
                            "accion": "crear_o_actualizar_producto",
                            "precio": str(producto.precio_importado.monto)
                            if producto.precio_importado
                            else None,
                            "stock": producto.stock.cantidad
                            if producto.stock
                            else None,
                            "imagenes": len(producto.imagenes),
                            "payload_preview": payload,
                            "categoria": producto.categoria_nombre,
                            "subcategoria": producto.subcategoria_nombre,
                            "descripcion_largo": len(producto.descripcion_web or ""),
                            "descripcion_preview": (producto.descripcion_web or "")[
                                :300
                            ],
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

                tn_product = (
                    resultado.detalles.get("tn_product", {})
                    if resultado.detalles
                    else {}
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
                            estado_publicacion="activo",
                        )

                self.audit_repo.registrar(
                    sku=producto.sku,
                    accion="TN_IMPORT_PRODUCT_TEST",
                    estado="OK",
                    mensaje=f"accion={accion} tn_product_id={tn_product_id or ''}",
                    metodo_gbp="AdaptadorTiendaNube.crear_o_actualizar_producto",
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
                        "precio": str(producto.precio_importado.monto)
                        if producto.precio_importado
                        else None,
                        "stock": producto.stock.cantidad if producto.stock else None,
                        "imagenes": len(producto.imagenes),
                        "categoria": producto.categoria_nombre,
                        "subcategoria": producto.subcategoria_nombre,
                        "descripcion_largo": len(producto.descripcion_web or ""),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - una fila no debe cortar el lote.
                logger.exception(
                    "tn_import_product_failed", extra={"sku": sku, "item_id": item_id}
                )
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
