from types import SimpleNamespace

import pytest

from app.aplicacion.pedidos.casos_uso.procesar_pedido_tienda_nube import (
    ProcesarPedidoTiendaNube,
)


class CasoUsoFalso:
    def __init__(self, resultado):
        self.resultado = resultado
        self.llamadas = []

    async def ejecutar(self, valor):
        self.llamadas.append(valor)
        return self.resultado


@pytest.mark.asyncio
async def test_orquesta_importacion_cliente_y_confirmacion() -> None:
    recepcion = SimpleNamespace(
        pedido_id=7,
        external_order_id="991",
        __dict__={"pedido_id": 7, "external_order_id": "991"},
    )
    importador = CasoUsoFalso(recepcion)
    creador = CasoUsoFalso({"cust_id": 42})
    confirmador = CasoUsoFalso({"gbp_order_id": "1234"})

    class ProveedorFalso:
        async def get_order(self, order_id):
            return {"payment_status": "paid", "status": "open"}

    resultado = await ProcesarPedidoTiendaNube(
        importador, creador, confirmador, ProveedorFalso()
    ).ejecutar("991")

    assert importador.llamadas == ["991"]
    assert creador.llamadas == [7]
    assert confirmador.llamadas == [7]
    assert resultado["pedido_gbp"]["gbp_order_id"] == "1234"


@pytest.mark.asyncio
@pytest.mark.parametrize("payment_status,status", [
    ("pending", "open"), ("authorized", "open"),
    ("paid", "cancelled"), ("paid", "voided"),
])
async def test_no_escribe_gbp_si_pago_no_confirmado_o_anulado(payment_status, status):
    class ProveedorFalso:
        async def get_order(self, order_id):
            return {"payment_status": payment_status, "status": status}
    importador = CasoUsoFalso(None)
    creador = CasoUsoFalso(None)
    confirmador = CasoUsoFalso(None)
    with pytest.raises(ValueError):
        await ProcesarPedidoTiendaNube(
            importador, creador, confirmador, ProveedorFalso()
        ).ejecutar("991")
    assert importador.llamadas == []
    assert creador.llamadas == []
    assert confirmador.llamadas == []
