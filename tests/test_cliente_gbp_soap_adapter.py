import pytest

from app.infraestructura.gbp.cliente import GBPCallResult
from app.infraestructura.gbp.clientes import ClienteGBPSoapAdapter, normalizar_texto_gbp


class ClienteSoapFalso:
    def __init__(self):
        self.calls = []

    async def autenticar(self):
        return "token"

    async def call_soap_method(self, method_name, *, token="", params=None):
        self.calls.append((method_name, token, params))
        if method_name == "States_funGetXMLData":
            return GBPCallResult(
                "<NewDataSet><Table><state_id>54018</state_id><state_desc>Tierra del Fuego</state_desc></Table></NewDataSet>",
                1,
            )
        if method_name == "Customers_setNEWCustomer":
            return GBPCallResult("56369", 1)
        if method_name == "CustomersByTaxNumber_funGetXMLData":
            return GBPCallResult("Not data found.", 1)
        raise AssertionError(method_name)


def test_normaliza_tildes_y_espacios():
    assert normalizar_texto_gbp("  Río   Grande  ") == "Rio Grande"


@pytest.mark.asyncio
async def test_alta_envia_ids_fiscales_y_textos_sin_tildes():
    soap = ClienteSoapFalso()
    adapter = ClienteGBPSoapAdapter(soap)

    cust_id = await adapter.crear_cliente(
        nombre="Melisa Elena Carmona",
        country_id=54,
        state_id=54018,
        direccion="Laguna Don Bosco 1636",
        ciudad="Río Grande",
        codigo_postal="9420",
        fiscal_class_id=2,
        tax_number_type_id=5,
        documento="33214438",
        email="CARMONA@EXAMPLE.COM",
        telefono="+54 2964 610324",
    )

    assert cust_id == 56369
    _, _, params = soap.calls[-1]
    assert params["pcountry"] == "54"
    assert params["pstate"] == "54018"
    assert params["pfiscalclass"] == "2"
    assert params["ptaxnumbertype"] == "5"
    assert params["pcity"] == "Rio Grande"
    assert params["pemail"] == "carmona@example.com"
    assert params["ppass1"] == ""
    assert params["ppass2"] == ""
