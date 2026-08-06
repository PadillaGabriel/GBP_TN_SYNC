from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoRecepcionPedido:
    pedido_id: int
    canal: str
    external_order_id: str
    creado: bool
    idempotente: bool
    estado_negocio: str
    estado_integracion: str
    etapa: str
