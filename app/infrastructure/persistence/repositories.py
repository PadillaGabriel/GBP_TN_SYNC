from datetime import UTC, datetime
from decimal import Decimal
import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.services.producto_validation_service import ResultadoValidacionProducto
from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.infrastructure.persistence.models import (
    DepositoEcommerceModel,
    ProductoFuenteModel,
    ProductoTiendaNubeModel,
    ProductoValidacionModel,
    StockActualModel,
    SyncAuditModel,
    SyncJobModel,
)


MAPEO_TN_ESTADOS_INACTIVOS = ("eliminado_tn", "eliminado_externo")


class ProductoRepository:
    """Repositorio de productos normalizados."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def guardar_producto(self, producto: Producto) -> ProductoFuenteModel:
        """Inserta o actualiza producto normalizado."""

        model = self.db.scalar(
            select(ProductoFuenteModel).where(ProductoFuenteModel.sku == producto.sku)
        )
        precio = producto.precio_importado.monto if producto.precio_importado else None
        medidas = producto.medidas
        if model is None:
            model = ProductoFuenteModel(
                id_sistema_gbp=producto.id_sistema_gbp,
                sku=producto.sku,
                titulo=producto.titulo,
            )
            self.db.add(model)

        model.codigo_universal = producto.codigo_universal
        model.codigo_proveedor = producto.codigo_proveedor
        model.titulo = producto.titulo
        model.categoria_nombre = producto.categoria_nombre
        model.subcategoria_nombre = producto.subcategoria_nombre
        model.marca_nombre = producto.marca_nombre
        model.publicable_web = producto.publicable_web
        model.item_disabled = producto.item_disabled
        model.item_not_for_sale = producto.item_not_for_sale
        model.descripcion_web = producto.descripcion_web
        model.alto = medidas.alto if medidas else None
        model.ancho = medidas.ancho if medidas else None
        model.largo = medidas.largo if medidas else None
        model.peso = medidas.peso if medidas else None
        model.volumen = medidas.volumen if medidas else None
        model.precio_importado = precio
        model.payload_hash = producto.payload_hash
        model.ultima_importacion_completa = datetime.now(UTC)
        model.ultima_validacion = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(model)
        return model

    def guardar_validacion(
        self,
        producto_id: int,
        producto: Producto,
        resultado: ResultadoValidacionProducto,
    ) -> None:
        """Guarda matriz explicable de validacion."""

        model = self.db.scalar(
            select(ProductoValidacionModel).where(
                ProductoValidacionModel.producto_fuente_id == producto_id
            )
        )
        if model is None:
            model = ProductoValidacionModel(producto_fuente_id=producto_id, decision="PENDIENTE")
            self.db.add(model)

        model.tiene_imagen_website = producto.tiene_imagen_website
        model.item_web = producto.publicable_web
        model.item_disabled = producto.item_disabled
        model.item_not_for_sale = producto.item_not_for_sale
        model.tiene_descripcion_web = producto.tiene_descripcion_web
        model.tiene_precio_online = producto.precio_online_valido
        model.stock_consultable = producto.stock is not None and producto.stock.consultable
        model.sku_valido = bool(producto.sku.strip())
        model.titulo_valido = bool(producto.titulo.strip())
        model.decision = resultado.decision
        model.motivos_bloqueo = ",".join(resultado.motivos_bloqueo)
        model.cumple = ",".join(resultado.cumple)
        model.validado_at = datetime.now(UTC)
        self.db.commit()

    def guardar_stock(self, producto_id: int, stock: StockProducto) -> None:
        """Guarda stock disponible por deposito y stock publicable."""

        for deposito in stock.depositos:
            model = self.db.scalar(
                select(StockActualModel).where(
                    StockActualModel.producto_fuente_id == producto_id,
                    StockActualModel.stor_id == deposito.stor_id,
                )
            )
            if model is None:
                model = StockActualModel(
                    producto_fuente_id=producto_id,
                    sku=stock.sku,
                    stor_id=deposito.stor_id,
                    stock_disponible_gbp=deposito.stock_disponible,
                )
                self.db.add(model)
            model.stock_disponible_gbp = deposito.stock_disponible
            model.stock_original_gbp = Decimal(str(deposito.stock_original))
            model.stock_publicable_tn = stock.cantidad if deposito.usado_para_tienda_nube else None
            model.usado_para_tienda_nube = deposito.usado_para_tienda_nube
            model.ultima_consulta_gbp = datetime.now(UTC)
        self.db.commit()


    def obtener_por_sku(self, sku: str) -> ProductoFuenteModel | None:
        """Obtiene producto fuente por SKU."""

        return self.db.scalar(select(ProductoFuenteModel).where(ProductoFuenteModel.sku == sku))


    def obtener_skus_auditados(self) -> set[str]:
        """Devuelve SKUs ya auditados/persistidos para evitar reprocesar desde el inicio."""

        rows = self.db.scalars(select(ProductoFuenteModel.sku)).all()
        return {str(sku).strip() for sku in rows if str(sku or "").strip()}


    def listar_skus_por_decision(self, decision: str, *, limit: int = 200) -> list[str]:
        """Lista SKUs por decisión vigente para reauditorías focalizadas."""

        rows = self.db.scalars(
            select(ProductoFuenteModel.sku)
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
            )
            .where(ProductoValidacionModel.decision == decision)
            .order_by(ProductoValidacionModel.validado_at.asc().nullsfirst())
            .limit(limit)
        ).all()
        return [str(sku).strip() for sku in rows if str(sku or '').strip()]

    def listar_publicables_para_importar(self, limit: int = 20) -> list[dict[str, object]]:
        """Lista productos validados como publicables para importación controlada.

        Excluye productos con mapeo activo en Tienda Nube para que los lotes de
        importación controlada no vuelvan a seleccionar los mismos SKUs. Si el
        mapeo local quedó marcado como eliminado_tn/eliminado_externo, el SKU
        vuelve a quedar disponible para una nueva carga controlada.
        """

        rows = self.db.execute(
            select(ProductoFuenteModel, ProductoValidacionModel, ProductoTiendaNubeModel)
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
            )
            .join(
                ProductoTiendaNubeModel,
                ProductoTiendaNubeModel.sku == ProductoFuenteModel.sku,
                isouter=True,
            )
            .where(ProductoValidacionModel.decision == "PUBLICABLE_AUTOMATICO")
            .where(
                or_(
                    ProductoTiendaNubeModel.id.is_(None),
                    ProductoTiendaNubeModel.estado_publicacion.in_(MAPEO_TN_ESTADOS_INACTIVOS),
                )
            )
            .order_by(ProductoFuenteModel.ultima_validacion.desc().nullslast())
            .limit(limit)
        ).all()
        return [
            {
                "id": producto.id,
                "sku": producto.sku,
                "id_sistema_gbp": producto.id_sistema_gbp,
                "titulo": producto.titulo,
                "decision": validacion.decision,
            }
            for producto, validacion, _mapeo in rows
        ]

    def guardar_mapeo_tienda_nube(
        self,
        *,
        producto_fuente_id: int,
        sku: str,
        tn_product_id: str,
        tn_variant_id: str | None = None,
        estado_publicacion: str = "activo",
    ) -> ProductoTiendaNubeModel:
        """Inserta o actualiza el mapeo GBP ↔ Tienda Nube."""

        model = self.db.scalar(
            select(ProductoTiendaNubeModel).where(ProductoTiendaNubeModel.sku == sku)
        )
        if model is None:
            model = ProductoTiendaNubeModel(
                producto_fuente_id=producto_fuente_id,
                sku=sku,
                tn_product_id=tn_product_id,
            )
            self.db.add(model)
        model.producto_fuente_id = producto_fuente_id
        model.tn_product_id = tn_product_id
        model.tn_variant_id = tn_variant_id
        model.estado_publicacion = estado_publicacion
        model.ultima_sync_completa = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(model)
        return model

    def contar_productos(self) -> int:
        """Cuenta productos importados localmente."""

        return int(self.db.scalar(select(func.count(ProductoFuenteModel.id))) or 0)

    def contar_por_decision(self) -> dict[str, int]:
        """Cuenta productos por decision de validacion."""

        rows = self.db.execute(
            select(ProductoValidacionModel.decision, func.count(ProductoValidacionModel.id)).group_by(
                ProductoValidacionModel.decision
            )
        ).all()
        return {str(decision): int(count) for decision, count in rows}

    def contar_mapeos_tienda_nube(self) -> int:
        """Cuenta productos con mapeo activo hacia Tienda Nube."""

        return int(
            self.db.scalar(
                select(func.count(ProductoTiendaNubeModel.id)).where(
                    ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS)
                )
            )
            or 0
        )

    def contar_mapeos_tienda_nube_locales(self) -> int:
        """Cuenta todos los mapeos locales, incluidos los marcados como eliminados."""

        return int(self.db.scalar(select(func.count(ProductoTiendaNubeModel.id))) or 0)

    def contar_mapeos_tienda_nube_eliminados(self) -> int:
        """Cuenta mapeos locales que ya no deben considerarse importados activos."""

        return int(
            self.db.scalar(
                select(func.count(ProductoTiendaNubeModel.id)).where(
                    ProductoTiendaNubeModel.estado_publicacion.in_(MAPEO_TN_ESTADOS_INACTIVOS)
                )
            )
            or 0
        )

    def contar_publicables_pendientes_importar(self) -> int:
        """Cuenta publicables sin mapeo en Tienda Nube."""

        return int(
            self.db.scalar(
                select(func.count(ProductoFuenteModel.id))
                .join(
                    ProductoValidacionModel,
                    ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
                )
                .join(
                    ProductoTiendaNubeModel,
                    ProductoTiendaNubeModel.sku == ProductoFuenteModel.sku,
                    isouter=True,
                )
                .where(ProductoValidacionModel.decision == "PUBLICABLE_AUTOMATICO")
                .where(
                    or_(
                        ProductoTiendaNubeModel.id.is_(None),
                        ProductoTiendaNubeModel.estado_publicacion.in_(MAPEO_TN_ESTADOS_INACTIVOS),
                    )
                )
            )
            or 0
        )

    def contar_bloqueados_importados(self) -> int:
        """Cuenta productos importados que hoy están bloqueados por la validación actual."""

        return int(
            self.db.scalar(
                select(func.count(ProductoTiendaNubeModel.id))
                .join(ProductoFuenteModel, ProductoFuenteModel.sku == ProductoTiendaNubeModel.sku)
                .join(
                    ProductoValidacionModel,
                    ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
                )
                .where(ProductoValidacionModel.decision != "PUBLICABLE_AUTOMATICO")
                .where(ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS))
            )
            or 0
        )

    def resumen_operativo_panel(self) -> dict[str, object]:
        """Devuelve métricas separadas para no confundir auditados con importados."""

        decisiones = self.contar_por_decision()
        productos_auditados = self.contar_productos()
        productos_mapeados = self.contar_mapeos_tienda_nube()
        publicables_total = int(decisiones.get("PUBLICABLE_AUTOMATICO", 0))
        bloqueados_total = max(productos_auditados - publicables_total, 0)
        return {
            "productos_auditados": productos_auditados,
            "productos_mapeados_tienda_nube": productos_mapeados,
            "productos_mapeados_locales": self.contar_mapeos_tienda_nube_locales(),
            "productos_mapeados_eliminados": self.contar_mapeos_tienda_nube_eliminados(),
            "publicables_total": publicables_total,
            "publicables_pendientes_importar": self.contar_publicables_pendientes_importar(),
            "bloqueados_total": bloqueados_total,
            "bloqueados_importados_tienda_nube": self.contar_bloqueados_importados(),
            "bloqueados_por_motivo": {
                decision: count
                for decision, count in decisiones.items()
                if decision != "PUBLICABLE_AUTOMATICO"
            },
        }

    def listar_panel_productos(self, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        """Lista productos con datos relevantes para el panel."""

        rows = self.db.execute(
            select(ProductoFuenteModel, ProductoValidacionModel)
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
                isouter=True,
            )
            .order_by(ProductoFuenteModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [self._to_panel_dict(producto, validacion) for producto, validacion in rows]


    def listar_productos_importados(self, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        """Lista productos con mapeo Tienda Nube para revisión post-importación."""

        rows = self.db.execute(
            select(ProductoFuenteModel, ProductoValidacionModel, ProductoTiendaNubeModel)
            .join(
                ProductoTiendaNubeModel,
                ProductoTiendaNubeModel.sku == ProductoFuenteModel.sku,
            )
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
                isouter=True,
            )
            .order_by(ProductoTiendaNubeModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            self._to_importado_dict(producto, validacion, mapeo)
            for producto, validacion, mapeo in rows
        ]

    def listar_productos_bloqueados(self, limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
        """Lista productos no importables con motivo visible para el panel."""

        rows = self.db.execute(
            select(ProductoFuenteModel, ProductoValidacionModel, ProductoTiendaNubeModel)
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
            )
            .join(
                ProductoTiendaNubeModel,
                ProductoTiendaNubeModel.sku == ProductoFuenteModel.sku,
                isouter=True,
            )
            .where(ProductoValidacionModel.decision != "PUBLICABLE_AUTOMATICO")
            .order_by(ProductoValidacionModel.validado_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            self._to_bloqueado_dict(producto, validacion, mapeo)
            for producto, validacion, mapeo in rows
        ]

    def obtener_mapeo_tienda_nube_por_sku(self, sku: str) -> ProductoTiendaNubeModel | None:
        """Obtiene mapeo local hacia Tienda Nube por SKU."""

        return self.db.scalar(select(ProductoTiendaNubeModel).where(ProductoTiendaNubeModel.sku == sku))

    def actualizar_estado_mapeo_tienda_nube(self, sku: str, estado_publicacion: str) -> ProductoTiendaNubeModel | None:
        """Actualiza estado operativo del mapeo local sin borrar auditoría."""

        model = self.obtener_mapeo_tienda_nube_por_sku(sku)
        if model is None:
            return None
        model.estado_publicacion = estado_publicacion
        model.ultima_sync_completa = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(model)
        return model

    def listar_mapeos_tienda_nube(self, limit: int = 500, offset: int = 0) -> list[ProductoTiendaNubeModel]:
        """Lista mapeos locales hacia Tienda Nube para reconciliación."""

        return list(
            self.db.scalars(
                select(ProductoTiendaNubeModel)
                .order_by(ProductoTiendaNubeModel.updated_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        )

    def marcar_todos_mapeos_como_eliminados_externos(self) -> int:
        """Marca todos los mapeos activos como eliminados externamente."""

        rows = list(
            self.db.scalars(
                select(ProductoTiendaNubeModel).where(
                    ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS)
                )
            ).all()
        )
        now = datetime.now(UTC)
        for row in rows:
            row.estado_publicacion = "eliminado_externo"
            row.ultima_sync_completa = now
        self.db.commit()
        return len(rows)

    def es_mapeo_tienda_nube_activo(self, mapeo: ProductoTiendaNubeModel | None) -> bool:
        """Indica si el mapeo representa una publicación vigente en Tienda Nube."""

        return bool(mapeo and mapeo.estado_publicacion not in MAPEO_TN_ESTADOS_INACTIVOS)

    def listar_panel_decisiones(
        self,
        *,
        estado: str = "requiere_revision",
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
    ) -> list[dict[str, object]]:
        """Lista productos para gestionar decisiones operativas desde el panel."""

        query = (
            select(
                ProductoFuenteModel,
                ProductoValidacionModel,
                ProductoTiendaNubeModel,
                StockActualModel.stock_publicable_tn,
            )
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
                isouter=True,
            )
            .join(
                ProductoTiendaNubeModel,
                ProductoTiendaNubeModel.sku == ProductoFuenteModel.sku,
                isouter=True,
            )
            .join(
                StockActualModel,
                (StockActualModel.producto_fuente_id == ProductoFuenteModel.id)
                & (StockActualModel.usado_para_tienda_nube.is_(True)),
                isouter=True,
            )
        )

        if estado == "bloqueado_importado":
            query = query.where(
                ProductoTiendaNubeModel.id.is_not(None),
                ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS),
                ProductoValidacionModel.decision != "PUBLICABLE_AUTOMATICO",
            )
        elif estado == "bloqueado":
            query = query.where(ProductoValidacionModel.decision != "PUBLICABLE_AUTOMATICO")
        elif estado == "importado":
            query = query.where(
                ProductoTiendaNubeModel.id.is_not(None),
                ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS),
            )
        elif estado == "publicable_pendiente":
            query = query.where(ProductoValidacionModel.decision == "PUBLICABLE_AUTOMATICO").where(
                or_(
                    ProductoTiendaNubeModel.id.is_(None),
                    ProductoTiendaNubeModel.estado_publicacion.in_(MAPEO_TN_ESTADOS_INACTIVOS),
                )
            )
        elif estado == "requiere_revision":
            query = query.where(
                ProductoTiendaNubeModel.id.is_not(None),
                ProductoTiendaNubeModel.estado_publicacion.notin_(MAPEO_TN_ESTADOS_INACTIVOS),
            ).where(
                (ProductoValidacionModel.decision != "PUBLICABLE_AUTOMATICO")
                | (StockActualModel.stock_publicable_tn <= 0)
            )
        elif estado != "todos":
            query = query.where(ProductoValidacionModel.decision == estado)

        clean_q = q.strip() if q else ""
        if clean_q:
            term = f"%{clean_q}%"
            query = query.where(
                or_(
                    ProductoFuenteModel.sku.ilike(term),
                    ProductoFuenteModel.titulo.ilike(term),
                    ProductoFuenteModel.categoria_nombre.ilike(term),
                    ProductoFuenteModel.subcategoria_nombre.ilike(term),
                    ProductoFuenteModel.marca_nombre.ilike(term),
                    ProductoFuenteModel.codigo_proveedor.ilike(term),
                    ProductoTiendaNubeModel.tn_product_id.ilike(term),
                )
            )

        rows = self.db.execute(
            query.order_by(ProductoFuenteModel.updated_at.desc()).offset(offset).limit(limit)
        ).all()
        return [
            self._to_decision_dict(producto, validacion, mapeo, stock_publicable)
            for producto, validacion, mapeo, stock_publicable in rows
        ]

    def _stock_publicable_tn(self, producto_id: int) -> int | None:
        """Devuelve stock publicable actual para Tienda Nube."""

        return self.db.scalar(
            select(StockActualModel.stock_publicable_tn).where(
                StockActualModel.producto_fuente_id == producto_id,
                StockActualModel.usado_para_tienda_nube.is_(True),
            )
        )

    def _to_decision_dict(
        self,
        producto: ProductoFuenteModel,
        validacion: ProductoValidacionModel | None,
        mapeo: ProductoTiendaNubeModel | None,
        stock_publicable: int | None,
    ) -> dict[str, object]:
        """Serializa un producto con acciones de decisión disponibles."""

        decision = validacion.decision if validacion else "SIN_VALIDAR"
        tuvo_mapeo = mapeo is not None
        importado = self.es_mapeo_tienda_nube_activo(mapeo)
        bloqueado = decision != "PUBLICABLE_AUTOMATICO"
        acciones: list[str] = []
        if importado:
            acciones.extend(["ocultar_tienda_nube", "eliminar_tienda_nube"])
        if not importado or bloqueado:
            acciones.append("importar_manual_forzada")
        if importado and bloqueado:
            acciones.append("mantener_importado_bajo_revision")
        return {
            "sku": producto.sku,
            "id_sistema_gbp": producto.id_sistema_gbp,
            "titulo": producto.titulo,
            "categoria": producto.categoria_nombre,
            "subcategoria": producto.subcategoria_nombre,
            "marca": producto.marca_nombre,
            "codigo_proveedor": producto.codigo_proveedor,
            "precio_importado": float(producto.precio_importado) if producto.precio_importado else None,
            "stock_publicable_tn": stock_publicable,
            "decision": decision,
            "motivos_bloqueo": validacion.motivos_bloqueo.split(",") if validacion and validacion.motivos_bloqueo else [],
            "descripcion_largo": len(producto.descripcion_web or ""),
            "ya_importado_tienda_nube": importado,
            "tuvo_mapeo_tienda_nube": tuvo_mapeo,
            "tn_product_id": mapeo.tn_product_id if mapeo else None,
            "tn_variant_id": mapeo.tn_variant_id if mapeo else None,
            "estado_publicacion": mapeo.estado_publicacion if mapeo else None,
            "requiere_revision": bool(importado and (bloqueado or (stock_publicable is not None and stock_publicable <= 0))),
            "acciones_disponibles": acciones,
            "endpoints": {
                "ocultar_tienda_nube": f"/admin/decisiones/productos/{producto.sku}/ocultar-tn?confirm=true" if importado else None,
                "eliminar_tienda_nube": f"/admin/decisiones/productos/{producto.sku}/eliminar-tn?confirm=true" if importado else None,
                "importar_manual_forzada": f"/sync/import/tienda-nube-manual?sku={producto.sku}&forzar=true&confirm=true",
            },
        }

    def _to_importado_dict(
        self,
        producto: ProductoFuenteModel,
        validacion: ProductoValidacionModel | None,
        mapeo: ProductoTiendaNubeModel,
    ) -> dict[str, object]:
        return {
            "sku": producto.sku,
            "id_sistema_gbp": producto.id_sistema_gbp,
            "titulo": producto.titulo,
            "categoria": producto.categoria_nombre,
            "subcategoria": producto.subcategoria_nombre,
            "marca": producto.marca_nombre,
            "codigo_proveedor": producto.codigo_proveedor,
            "precio_importado": float(producto.precio_importado) if producto.precio_importado else None,
            "stock_publicable_tn": self._stock_publicable_tn(producto.id),
            "decision": validacion.decision if validacion else "SIN_VALIDAR",
            "motivos_bloqueo": validacion.motivos_bloqueo.split(",") if validacion and validacion.motivos_bloqueo else [],
            "tn_product_id": mapeo.tn_product_id,
            "tn_variant_id": mapeo.tn_variant_id,
            "estado_publicacion": mapeo.estado_publicacion,
            "ultima_sync_completa": mapeo.ultima_sync_completa.isoformat() if mapeo.ultima_sync_completa else None,
            "created_at": mapeo.created_at.isoformat() if mapeo.created_at else None,
            "updated_at": mapeo.updated_at.isoformat() if mapeo.updated_at else None,
        }

    def _to_bloqueado_dict(
        self,
        producto: ProductoFuenteModel,
        validacion: ProductoValidacionModel,
        mapeo: ProductoTiendaNubeModel | None,
    ) -> dict[str, object]:
        data = self._to_panel_dict(producto, validacion)
        data.update(
            {
                "stock_publicable_tn": self._stock_publicable_tn(producto.id),
                "descripcion_largo": len(producto.descripcion_web or ""),
                "ya_importado_tienda_nube": self.es_mapeo_tienda_nube_activo(mapeo),
                "tuvo_mapeo_tienda_nube": mapeo is not None,
                "tn_product_id": mapeo.tn_product_id if mapeo else None,
                "accion_manual_disponible": True,
                "endpoint_importacion_manual": f"/sync/import/tienda-nube-manual?sku={producto.sku}&forzar=true&confirm=true",
            }
        )
        return data

    @staticmethod
    def _to_panel_dict(
        producto: ProductoFuenteModel,
        validacion: ProductoValidacionModel | None,
    ) -> dict[str, object]:
        return {
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
            "tiene_descripcion_web": bool((producto.descripcion_web or "").strip()),
            "precio_importado": float(producto.precio_importado) if producto.precio_importado else None,
            "decision": validacion.decision if validacion else "SIN_VALIDAR",
            "motivos_bloqueo": validacion.motivos_bloqueo.split(",") if validacion and validacion.motivos_bloqueo else [],
            "ultima_validacion": producto.ultima_validacion.isoformat() if producto.ultima_validacion else None,
        }


class DepositoRepository:
    """Repositorio de depositos habilitados para ecommerce."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def listar_habilitados(self) -> list[str]:
        """Lista stor_id habilitados para calcular stock TN."""

        rows = self.db.scalars(
            select(DepositoEcommerceModel).where(DepositoEcommerceModel.habilitado_tn.is_(True))
        ).all()
        return [row.stor_id for row in rows]

    def listar(self) -> list[dict[str, object]]:
        """Lista depositos configurados."""

        rows = self.db.scalars(select(DepositoEcommerceModel).order_by(DepositoEcommerceModel.stor_id)).all()
        return [
            {
                "stor_id": row.stor_id,
                "nombre": row.nombre,
                "habilitado_tn": row.habilitado_tn,
                "observacion": row.observacion,
            }
            for row in rows
        ]


class SyncAuditRepository:
    """Repositorio de auditoria."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def registrar(
        self,
        *,
        sku: str | None,
        accion: str,
        estado: str,
        mensaje: str,
        metodo_gbp: str | None = None,
        duracion_ms: int | None = None,
    ) -> None:
        """Registra operacion auditada."""

        self.db.add(
            SyncAuditModel(
                sku=sku,
                accion=accion,
                metodo_gbp=metodo_gbp,
                duracion_ms=duracion_ms,
                estado=estado,
                mensaje=mensaje,
            )
        )
        self.db.commit()

    def obtener_ultimo_evento(self) -> dict[str, object] | None:
        """Devuelve ultimo evento auditado."""

        event = self.db.scalars(
            select(SyncAuditModel).order_by(SyncAuditModel.created_at.desc()).limit(1)
        ).first()
        if event is None:
            return None
        return {
            "sku": event.sku,
            "accion": event.accion,
            "metodo_gbp": event.metodo_gbp,
            "duracion_ms": event.duracion_ms,
            "estado": event.estado,
            "mensaje": event.mensaje,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }


class SyncJobRepository:
    """Repositorio de jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def crear(
        self,
        *,
        tipo: str,
        sku: str | None = None,
        id_sistema_gbp: str | None = None,
        prioridad: int = 100,
        progreso: dict[str, object] | None = None,
    ) -> SyncJobModel:
        """Crea un job persistido para ejecución larga."""

        job = SyncJobModel(
            tipo=tipo,
            estado="PENDIENTE",
            sku=sku,
            id_sistema_gbp=id_sistema_gbp,
            prioridad=prioridad,
            error_mensaje=json.dumps(progreso or {}, ensure_ascii=False),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def obtener(self, job_id: int) -> SyncJobModel | None:
        """Obtiene un job por id."""

        return self.db.get(SyncJobModel, job_id)

    def actualizar(
        self,
        job_id: int,
        *,
        estado: str | None = None,
        progreso: dict[str, object] | None = None,
        error_codigo: str | None = None,
        error_mensaje: str | None = None,
        iniciar: bool = False,
        finalizar: bool = False,
    ) -> SyncJobModel | None:
        """Actualiza estado y progreso del job."""

        job = self.obtener(job_id)
        if job is None:
            return None
        if estado is not None:
            job.estado = estado
        if iniciar:
            job.started_at = datetime.now(UTC)
        if finalizar:
            job.finished_at = datetime.now(UTC)
        if error_codigo is not None:
            job.error_codigo = error_codigo
        if progreso is not None:
            job.error_mensaje = json.dumps(progreso, ensure_ascii=False)
        elif error_mensaje is not None:
            job.error_mensaje = error_mensaje
        self.db.commit()
        self.db.refresh(job)
        return job

    def serializar(self, job: SyncJobModel | None) -> dict[str, object] | None:
        """Serializa un job para API/panel."""

        if job is None:
            return None
        progreso: object = {}
        if job.error_mensaje:
            try:
                progreso = json.loads(job.error_mensaje)
            except json.JSONDecodeError:
                progreso = {"mensaje": job.error_mensaje}
        return {
            "id": job.id,
            "tipo": job.tipo,
            "estado": job.estado,
            "sku": job.sku,
            "id_sistema_gbp": job.id_sistema_gbp,
            "prioridad": job.prioridad,
            "intentos": job.intentos,
            "error_codigo": job.error_codigo,
            "progreso": progreso,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }

    def obtener_serializado(self, job_id: int) -> dict[str, object] | None:
        """Obtiene y serializa un job."""

        return self.serializar(self.obtener(job_id))

    def contar_por_estado(self) -> dict[str, int]:
        """Cuenta jobs por estado."""

        rows = self.db.execute(
            select(SyncJobModel.estado, func.count(SyncJobModel.id)).group_by(SyncJobModel.estado)
        ).all()
        return {str(estado): int(count) for estado, count in rows}
