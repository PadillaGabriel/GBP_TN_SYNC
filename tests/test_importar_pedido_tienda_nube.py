import asyncio
from decimal import Decimal

import pytest

from app.aplicacion.pedidos.casos_uso.importar_pedido_tienda_nube import (
    ImportarPedidoTiendaNube,
    PedidoTiendaNubeInvalidoError,
    PedidoTiendaNubeNoEncontradoError,
)


class ProveedorFalso:
    def __init__(self, payload):
        self.payload = payload

    async def get_order(self, order_id: str):
        return self.payload


class RepositorioFalso:
    def __init__(self):
        self.pedido = None

    def recibir_idempotente(self, pedido, request_id, correlation_id):
        self.pedido = pedido
        return type(
            "Resultado",
            (),
            {
                "pedido_id": 7,
                "canal": pedido.canal,
                "external_order_id": pedido.external_order_id,
                "creado": True,
                "idempotente": False,
                "estado_negocio": "RECIBIDO",
                "estado_integracion": "PENDIENTE",
                "etapa": "RECIBIDO",
            },
        )()


def payload_valido():
    return {
        "id": 2036396251,
        "token": "NO_DEBE_PERSISTIRSE",
        "number": 364,
        "currency": "ARS",
        "total": "109189.54",
        "created_at": "2026-08-04T12:32:32+0000",
        "customer": {
            "id": 324102676,
            "name": "Melisa Elena Carmona",
            "email": "cliente@example.com",
            "phone": "+540000000",
            "identification": "33214438",
        },
        "shipping_address": {
            "name": "Melisa Elena Carmona",
            "address": "Laguna Don Bosco",
            "number": "1636",
            "city": "Río Grande",
            "province": "Tierra del Fuego",
            "zipcode": "9420",
            "country": "AR",
        },
        "products": [
            {
                "id": 3422103740,
                "variant_id": "1538674690",
                "sku": "7275",
                "quantity": "1",
                "price": "12000.00",
                "name": "Tetera",
            }
        ],
    }


def test_importa_y_sanitiza_token():
    repo = RepositorioFalso()
    resultado = asyncio.run(
        ImportarPedidoTiendaNube(ProveedorFalso(payload_valido()), repo).ejecutar(
            "2036396251"
        )
    )
    assert resultado.pedido_id == 7
    assert repo.pedido.external_order_id == "2036396251"
    assert repo.pedido.total == Decimal("109189.54")
    assert repo.pedido.items[0].sku == "7275"
    assert "token" not in repo.pedido.payload_crudo


def test_404_controlado():
    with pytest.raises(PedidoTiendaNubeNoEncontradoError):
        asyncio.run(
            ImportarPedidoTiendaNube(ProveedorFalso(None), RepositorioFalso()).ejecutar(
                "1"
            )
        )


def test_rechaza_producto_sin_sku():
    payload = payload_valido()
    payload["products"][0]["sku"] = ""
    with pytest.raises(PedidoTiendaNubeInvalidoError):
        asyncio.run(
            ImportarPedidoTiendaNube(
                ProveedorFalso(payload), RepositorioFalso()
            ).ejecutar("1")
        )
