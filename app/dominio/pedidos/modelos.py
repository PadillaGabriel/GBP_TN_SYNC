from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class EstadoNegocioPedido(StrEnum):
    RECIBIDO = "RECIBIDO"
    VALIDADO = "VALIDADO"
    FACTURABLE = "FACTURABLE"
    REQUIERE_REVISION = "REQUIERE_REVISION"
    CANCELADO = "CANCELADO"


class EstadoIntegracionPedido(StrEnum):
    PENDIENTE = "PENDIENTE"
    PROCESANDO = "PROCESANDO"
    ENVIADO_A_GBP = "ENVIADO_A_GBP"
    CONFIRMADO = "CONFIRMADO"
    ERROR_FUNCIONAL = "ERROR_FUNCIONAL"
    ERROR_TECNICO = "ERROR_TECNICO"


class EtapaProcesamientoPedido(StrEnum):
    RECIBIDO = "RECIBIDO"
    CLIENTE_PENDIENTE = "CLIENTE_PENDIENTE"
    PRODUCTOS_PENDIENTES = "PRODUCTOS_PENDIENTES"
    STOCK_PENDIENTE = "STOCK_PENDIENTE"
    LISTO_PARA_GBP = "LISTO_PARA_GBP"


@dataclass(frozen=True)
class ItemPedidoExterno:
    external_item_id: str
    external_variant_id: str | None
    sku: str
    cantidad: int
    precio_unitario: Decimal
    descuento: Decimal = Decimal("0")
    titulo: str | None = None


@dataclass(frozen=True)
class ClientePedidoExterno:
    external_customer_id: str | None
    nombre: str
    apellido: str
    email: str | None = None
    telefono: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None


@dataclass(frozen=True)
class DireccionEnvioPedido:
    destinatario: str
    direccion: str
    ciudad: str
    provincia: str
    codigo_postal: str
    pais: str = "AR"


@dataclass(frozen=True)
class PedidoExterno:
    canal: str
    external_order_id: str
    numero_pedido: str | None
    moneda: str
    total: Decimal
    creado_en: datetime
    cliente: ClientePedidoExterno
    items: tuple[ItemPedidoExterno, ...]
    envio: DireccionEnvioPedido | None = None
    payload_crudo: dict = field(default_factory=dict)
