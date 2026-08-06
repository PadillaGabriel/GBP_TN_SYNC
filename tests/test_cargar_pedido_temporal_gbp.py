from decimal import Decimal

import pytest

from app.aplicacion.pedidos.casos_uso.cargar_pedido_temporal_gbp import (
    CargarPedidoTemporalGBP,
    CargaTemporalGBPDeshabilitadaError,
    analizar_totales_gbp,
)
from app.configuracion import ConfiguracionAplicacion


class Preparador:
    async def ejecutar(self, pedido_id):
        return {
            "cliente_gbp_id": 56369,
            "totales": {"total_esperado": "109189.54"},
            "pedido": {
                "tipo_documento_id": 1,
                "items": [
                    {
                        "tipo": "PRODUCTO",
                        "sku": "7275",
                        "item_id": 13073,
                        "deposito_id": 18,
                        "lista_precio_id": 4,
                        "cantidad": "1",
                        "precio_final_tn": "12000",
                        "precio_neto_gbp": "9917.355372",
                        "iva_porcentaje": "21",
                        "iva_fuente": "DEFAULT_CONFIG",
                        "moneda_id": 1,
                    },
                    {
                        "tipo": "ENVIO",
                        "sku": "ENVIO",
                        "item_id": 7774,
                        "deposito_id": 18,
                        "lista_precio_id": 4,
                        "cantidad": "1",
                        "precio_final_tn": "15191.54",
                        "precio_neto_gbp": "12554.991736",
                        "iva_porcentaje": "21",
                        "iva_fuente": "DEFAULT_CONFIG",
                        "moneda_id": 1,
                    },
                ],
            },
        }


class Cliente:
    def __init__(self, total="109189.54"):
        self.items = []
        self.total = total

    async def autenticar(self):
        return "token"

    async def obtener_identificador(self, token):
        return "GUID-1"

    async def mantener_vivo(self, token, guid):
        return "1"

    async def insertar_item(self, token, **kwargs):
        self.items.append(kwargs)
        return "<NewDataSet><Table><code>1</code><error_description>Insert OK</error_description></Table></NewDataSet>"

    async def obtener_datos_por_guid(self, token, guid):
        return "<NewDataSet/>"

    async def obtener_totales(self, token, **kwargs):
        return f"<NewDataSet><Table><ErrorCode>0</ErrorCode><Total>{self.total}</Total><TotalNeto>90239.29</TotalNeto><TotalTaxes>18950.25</TotalTaxes><TotalDiscount>0</TotalDiscount></Table></NewDataSet>"


@pytest.mark.asyncio
async def test_bloquea_staging_por_defecto():
    cfg = ConfiguracionAplicacion(
        _env_file=None,
        dry_run=True,
        pedidos_escritura_gbp_habilitada=False,
        pedidos_gbp_staging_enabled=False,
        pedidos_gbp_confirmation_enabled=False,
    )
    with pytest.raises(CargaTemporalGBPDeshabilitadaError):
        await CargarPedidoTemporalGBP(Preparador(), Cliente(), cfg).ejecutar(1)


@pytest.mark.asyncio
async def test_carga_neto_y_concilia_sin_confirmar():
    cfg = ConfiguracionAplicacion(
        _env_file=None, dry_run=False, pedidos_gbp_staging_enabled=True
    )
    cliente = Cliente()
    resultado = await CargarPedidoTemporalGBP(Preparador(), cliente, cfg).ejecutar(1)
    assert resultado["guid"] == "GUID-1"
    assert resultado["pedido_confirmado"] is False
    assert resultado["conciliacion_gbp"]["conciliado"] is True
    assert resultado["apto_para_confirmacion_futura"] is True
    assert cliente.items[0]["precio"] == Decimal("9917.355372")
    assert cliente.items[1]["cantidad"] == Decimal("1")


@pytest.mark.asyncio
async def test_marca_total_no_conciliado():
    cfg = ConfiguracionAplicacion(
        _env_file=None, dry_run=False, pedidos_gbp_staging_enabled=True
    )
    resultado = await CargarPedidoTemporalGBP(
        Preparador(), Cliente(total="100000"), cfg
    ).ejecutar(1)
    assert resultado["conciliacion_gbp"]["conciliado"] is False
    assert "TOTAL_GBP_NO_CONCILIADO" in resultado["bloqueos"]


def test_analiza_totales_gbp():
    xml = "<NewDataSet><Table><ErrorCode>0</ErrorCode><Total>121.00</Total><TotalNeto>100</TotalNeto><TotalTaxes>21</TotalTaxes><TotalDiscount>0</TotalDiscount></Table></NewDataSet>"
    r = analizar_totales_gbp(xml, Decimal("121"), Decimal("0.01"))
    assert r["conciliado"] is True
    assert r["diferencia"] == "0.00"


class PreparadorConCupon:
    async def ejecutar(self, pedido_id):
        return {
            "cliente_gbp_id": 1,
            "totales": {"total_esperado": "456160.56"},
            "pedido": {
                "tipo_documento_id": 1,
                "items": [
                    {
                        "tipo": "PRODUCTO",
                        "sku": "8567",
                        "item_id": 10509,
                        "deposito_id": 18,
                        "lista_precio_id": 4,
                        "cantidad": "1",
                        "precio_final_tn": "39999.00",
                        "precio_neto_gbp": "33057.024793",
                        "iva_porcentaje": "21",
                        "iva_fuente": "DEFAULT_CONFIG",
                        "moneda_id": 1,
                    },
                    {
                        "tipo": "DESCUENTO",
                        "sku": "CUPON",
                        "item_id": 11238,
                        "deposito_id": 18,
                        "lista_precio_id": 4,
                        "cantidad": "-1",
                        "precio_final_tn": "79122.00",
                        "precio_neto_gbp": "65390.082645",
                        "precio_final": "65390.082645",
                        "iva_porcentaje": "21",
                        "iva_fuente": "DEFAULT_CONFIG",
                        "moneda_id": 1,
                    },
                ],
            },
        }


class ClienteConResidual(Cliente):
    def __init__(self):
        super().__init__()
        self.guid_numero = 0
        self.totales = iter(["456160.53", "456160.56"])

    async def obtener_identificador(self, token):
        self.guid_numero += 1
        return f"GUID-{self.guid_numero}"

    async def obtener_datos_por_guid(self, token, guid):
        return """<NewDataSet>
        <Table><item_id>20001</item_id><item_code>C1</item_code><item_desc>Componente</item_desc><tis_qty>1</tis_qty><tis_price>100</tis_price><stor_id>18</stor_id></Table>
        <Table><item_id>11238</item_id><item_code>CUPON</item_code><item_desc>Cupon</item_desc><tis_qty>-1</tis_qty><tis_price>65390</tis_price><stor_id>18</stor_id></Table>
        </NewDataSet>"""

    async def obtener_totales(self, token, **kwargs):
        total = next(self.totales)
        return f"<NewDataSet><Table><ErrorCode>0</ErrorCode><Total>{total}</Total><TotalNeto>1</TotalNeto><TotalTaxes>1</TotalTaxes><TotalDiscount>0</TotalDiscount></Table></NewDataSet>"


@pytest.mark.asyncio
async def test_reintenta_en_nuevo_guid_y_ajusta_cupon_por_residuo():
    cfg = ConfiguracionAplicacion(
        _env_file=None,
        dry_run=False,
        pedidos_gbp_staging_enabled=True,
        pedidos_gbp_residual_maximo_ajustable=Decimal("0.05"),
    )
    cliente = ClienteConResidual()
    resultado = await CargarPedidoTemporalGBP(
        PreparadorConCupon(), cliente, cfg
    ).ejecutar(2)

    assert resultado["guid_inicial_descartado"] == "GUID-1"
    assert resultado["guid"] == "GUID-2"
    assert resultado["ajuste_residual"]["descuento_ajustado"] == "79121.97"
    assert resultado["conciliacion_gbp"]["conciliado"] is True
    assert resultado["expansion_gbp"]["expansion_detectada"] is True
    assert resultado["expansion_gbp"]["padres_expandidos"] == [10509]
    precios_cupon = [
        item["precio"] for item in cliente.items if item["item_id"] == 11238
    ]
    assert precios_cupon[-1] == Decimal("65390.057851")
