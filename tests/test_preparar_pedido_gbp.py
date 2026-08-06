from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.pedidos.casos_uso.preparar_pedido_gbp import (
    ClienteGBPNoVinculadoError,
    PrepararPedidoVentaGBP,
    calcular_componentes_financieros,
    convertir_precio_final_a_neto,
)
from app.configuracion import ConfiguracionAplicacion


class Repo:
    def __init__(self, cliente_id=56369, *, total="109189.54", payload=None):
        self.cliente_id = cliente_id
        self.total = total
        self.payload = payload or {}

    def obtener_por_id_para_validacion(self, pedido_id):
        return {
            "id": pedido_id,
            "total": self.total,
            "payload_crudo": self.payload,
            "cliente": {"gbp_customer_id": self.cliente_id} if self.cliente_id else {},
            "items": [
                {"sku": "7275", "quantity": 1, "unit_price": "12000", "discount": "0"},
                {"sku": "6043", "quantity": 1, "unit_price": "22499", "discount": "0"},
                {"sku": "10584", "quantity": 1, "unit_price": "59499", "discount": "0"},
            ],
        }


class Cliente:
    async def autenticar(self):
        return "token"

    async def obtener_item_id_por_codigo(self, token, sku):
        return {"7275": "13073", "6043": "10075", "10584": "12217", "CUPON": "999"}.get(
            sku
        )


@pytest.mark.asyncio
async def test_prepara_plan_con_precios_netos_y_envio_por_item_id():
    cfg = ConfiguracionAplicacion(_env_file=None)
    resultado = await PrepararPedidoVentaGBP(Repo(), Cliente(), cfg).ejecutar(1)
    assert resultado["modo"] == "SIMULACION"
    producto = resultado["pedido"]["items"][0]
    assert producto["precio_final_tn"] == "12000"
    assert producto["precio_neto_gbp"] == "9917.355372"
    assert producto["iva_porcentaje"] == "21"
    envio = resultado["pedido"]["items"][-1]
    assert envio["tipo"] == "ENVIO"
    assert envio["item_id"] == 7774
    assert envio["cantidad"] == "1"
    assert envio["precio_neto_gbp"] == "12554.991736"
    assert envio["precio_final_unitario_gbp_con_iva"] == "15191.54"


@pytest.mark.asyncio
async def test_prepara_cupon_cantidad_menos_uno_y_neto():
    cfg = ConfiguracionAplicacion(_env_file=None)
    repo = Repo(total="88998", payload={"discount": "5000", "shipping_cost": "0"})
    resultado = await PrepararPedidoVentaGBP(repo, Cliente(), cfg).ejecutar(1)
    cupon = resultado["pedido"]["items"][-1]
    assert cupon["tipo"] == "DESCUENTO"
    assert cupon["sku"] == "CUPON"
    assert cupon["cantidad"] == "-1"
    assert cupon["precio_neto_gbp"] == "4132.231405"


def test_override_iva_por_sku():
    cfg = ConfiguracionAplicacion(
        _env_file=None,
        pedidos_gbp_vat_rate_overrides='{"7275": 10.5, "ENVIO": 21}',
    )
    caso = PrepararPedidoVentaGBP(Repo(), Cliente(), cfg)
    precio, tasa, fuente = caso._precio_gbp(sku="7275", precio_final=Decimal("12000"))
    assert tasa == Decimal("10.5")
    assert fuente == "OVERRIDE_SKU"
    assert precio == Decimal("10859.728507")


def test_conversion_precio_neto_21():
    assert convertir_precio_final_a_neto(Decimal("121"), Decimal("21")) == Decimal(
        "100.000000"
    )


def test_calculo_componentes_por_reconciliacion():
    componentes = calcular_componentes_financieros(
        Repo().obtener_por_id_para_validacion(1)
    )
    assert componentes["subtotal_productos"] == Decimal("93998")
    assert componentes["envio"] == Decimal("15191.54")
    assert componentes["diferencia"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_exige_cliente_vinculado():
    cfg = ConfiguracionAplicacion(_env_file=None)
    with pytest.raises(ClienteGBPNoVinculadoError):
        await PrepararPedidoVentaGBP(Repo(cliente_id=None), Cliente(), cfg).ejecutar(1)
