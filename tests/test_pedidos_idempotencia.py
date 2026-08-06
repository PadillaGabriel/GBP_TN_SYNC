from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.aplicacion.pedidos.casos_uso import RecibirPedido
from app.dominio.pedidos import ClientePedidoExterno, ItemPedidoExterno, PedidoExterno
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.repositorios.pedidos import RepositorioPedidos


def crear_pedido() -> PedidoExterno:
    return PedidoExterno(
        canal="TIENDA_NUBE",
        external_order_id="12345",
        numero_pedido="TN-12345",
        moneda="ARS",
        total=Decimal("1500.00"),
        creado_en=datetime.now(UTC),
        cliente=ClientePedidoExterno(
            external_customer_id="c1", nombre="Ana", apellido="Pérez"
        ),
        items=(ItemPedidoExterno("i1", "v1", "SKU-1", 2, Decimal("750.00")),),
        payload_crudo={"id": 12345},
    )


def test_recepcion_es_idempotente() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sesion:
        caso = RecibirPedido(RepositorioPedidos(sesion))
        primero = caso.ejecutar(crear_pedido(), "req-1", "corr-1")
        segundo = caso.ejecutar(crear_pedido(), "req-2", "corr-2")

        assert primero.creado is True
        assert segundo.creado is False
        assert segundo.idempotente is True
        assert primero.pedido_id == segundo.pedido_id


def test_rechaza_cantidad_invalida() -> None:
    pedido = crear_pedido()
    invalido = PedidoExterno(
        **{
            **pedido.__dict__,
            "items": (ItemPedidoExterno("i1", None, "SKU", 0, Decimal("1")),),
        }
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with (
        Session(engine) as sesion,
        pytest.raises(ValueError, match="mayores que cero"),
    ):
        RecibirPedido(RepositorioPedidos(sesion)).ejecutar(
            invalido,
            "r",
            "c",
        )
