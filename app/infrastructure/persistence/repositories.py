from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
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

    def listar_publicables_para_importar(self, limit: int = 20) -> list[dict[str, object]]:
        """Lista productos validados como publicables para importación controlada."""

        rows = self.db.execute(
            select(ProductoFuenteModel, ProductoValidacionModel)
            .join(
                ProductoValidacionModel,
                ProductoValidacionModel.producto_fuente_id == ProductoFuenteModel.id,
            )
            .where(ProductoValidacionModel.decision == "PUBLICABLE_AUTOMATICO")
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
            for producto, validacion in rows
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

    def contar_por_estado(self) -> dict[str, int]:
        """Cuenta jobs por estado."""

        rows = self.db.execute(
            select(SyncJobModel.estado, func.count(SyncJobModel.id)).group_by(SyncJobModel.estado)
        ).all()
        return {str(estado): int(count) for estado, count in rows}
