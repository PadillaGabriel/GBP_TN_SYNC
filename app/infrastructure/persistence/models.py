from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.database import Base


class ProductoFuenteModel(Base):
    """Producto GBP normalizado y visible en el panel."""

    __tablename__ = "productos_fuente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_sistema_gbp: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    titulo: Mapped[str] = mapped_column(String(300))
    codigo_universal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    codigo_proveedor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    categoria_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subcategoria_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    marca_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publicable_web: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    item_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    item_not_for_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    descripcion_web: Mapped[str | None] = mapped_column(Text, nullable=True)
    alto: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    ancho: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    largo: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    peso: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    volumen: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    precio_importado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_crudo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultima_importacion_completa: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_validacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    stock: Mapped[list["StockActualModel"]] = relationship(back_populates="producto")
    validacion: Mapped["ProductoValidacionModel"] = relationship(back_populates="producto")


class ProductoValidacionModel(Base):
    """Matriz de validacion visible en el panel."""

    __tablename__ = "producto_validaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_fuente_id: Mapped[int] = mapped_column(ForeignKey("productos_fuente.id"), unique=True)
    tiene_imagen_website: Mapped[bool] = mapped_column(Boolean, default=False)
    item_web: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    item_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    item_not_for_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    tiene_descripcion_web: Mapped[bool] = mapped_column(Boolean, default=False)
    tiene_precio_online: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_consultable: Mapped[bool] = mapped_column(Boolean, default=False)
    sku_valido: Mapped[bool] = mapped_column(Boolean, default=False)
    titulo_valido: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(100), index=True)
    motivos_bloqueo: Mapped[str] = mapped_column(Text, default="")
    cumple: Mapped[str] = mapped_column(Text, default="")
    validado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    producto: Mapped[ProductoFuenteModel] = relationship(back_populates="validacion")


class StockActualModel(Base):
    """Stock disponible por deposito."""

    __tablename__ = "stock_actual"
    __table_args__ = (UniqueConstraint("producto_fuente_id", "stor_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_fuente_id: Mapped[int] = mapped_column(ForeignKey("productos_fuente.id"))
    sku: Mapped[str] = mapped_column(String(100), index=True)
    stor_id: Mapped[str] = mapped_column(String(50), index=True)
    stock_disponible_gbp: Mapped[int] = mapped_column(Integer)
    stock_original_gbp: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    stock_publicable_tn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usado_para_tienda_nube: Mapped[bool] = mapped_column(Boolean, default=False)
    ultima_consulta_gbp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_actualizacion_tn: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[str] = mapped_column(String(50), default="activo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    producto: Mapped[ProductoFuenteModel] = relationship(back_populates="stock")


class ProductoTiendaNubeModel(Base):
    """Mapeo GBP - Tienda Nube."""

    __tablename__ = "productos_tienda_nube"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_fuente_id: Mapped[int] = mapped_column(ForeignKey("productos_fuente.id"))
    tn_product_id: Mapped[str] = mapped_column(String(100), index=True)
    tn_variant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    estado_publicacion: Mapped[str] = mapped_column(String(50), default="activo")
    ultima_sync_stock: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_sync_completa: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DepositoEcommerceModel(Base):
    """Depositos habilitados para calcular stock publicable."""

    __tablename__ = "depositos_ecommerce"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stor_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    habilitado_tn: Mapped[bool] = mapped_column(Boolean, default=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncJobModel(Base):
    """Cola persistida de trabajos."""

    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(100), index=True)
    estado: Mapped[str] = mapped_column(String(50), index=True, default="PENDIENTE")
    sku: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    id_sistema_gbp: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    prioridad: Mapped[int] = mapped_column(Integer, default=100)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    error_codigo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncAuditModel(Base):
    """Auditoria de operaciones de integracion."""

    __tablename__ = "sync_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    accion: Mapped[str] = mapped_column(Text, index=True)
    metodo_gbp: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracion_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(Text, index=True)
    mensaje: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())