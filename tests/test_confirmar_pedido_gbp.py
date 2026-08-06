import pytest

from app.aplicacion.pedidos.casos_uso.confirmar_pedido_gbp import (
    ConfirmacionPedidoGBPDeshabilitadaError,
    ConfirmarPedidoGBP,
    PedidoGBPNoConciliadoError,
)
from app.configuracion import ConfiguracionAplicacion


class Preparador:
    async def ejecutar(self, pedido_id):
        return {
            "cliente_gbp_id": 56369,
            "totales": {"total_esperado": "100.00"},
            "pedido": {
                "tipo_documento_id": 1,
                "condicion_venta_id": 20,
                "transporte_id": 1,
                "descuento_id": 1,
                "observaciones": {
                    "observacion_1": "ORIGEN: TIENDANUBE",
                    "observacion_2": "TN_ORDER_ID: 123",
                    "observacion_3": "TN_ORDER_NUMBER: 1001",
                    "observacion_4": "INTEGRADOR: GBP_TN_SYNC",
                },
                "items": [
                    {
                        "tipo": "PRODUCTO",
                        "sku": "A",
                        "item_id": 1,
                        "deposito_id": 18,
                        "lista_precio_id": 4,
                        "cantidad": "1",
                        "precio_final_tn": "100.00",
                        "precio_neto_gbp": "82.644628",
                        "iva_porcentaje": "21",
                        "iva_fuente": "DEFAULT_CONFIG",
                        "moneda_id": 1,
                    }
                ],
            },
        }


class Repositorio:
    def __init__(self, existente=None):
        self.existente = existente
        self.guardado = None
        self.en_curso = False
        self.error = None

    def obtener_gbp_guid(self, pedido_id):
        return "GUID-GUARDADO" if self.existente else None

    def iniciar_confirmacion_gbp(self, pedido_id):
        if self.en_curso:
            return False
        self.en_curso = True
        return True

    def cancelar_confirmacion_gbp(self, pedido_id, motivo):
        self.error = motivo
        self.en_curso = False

    def obtener_gbp_order_id(self, pedido_id):
        return self.existente

    def confirmar_pedido_gbp(self, pedido_id, order_id, guid):
        self.guardado = (pedido_id, order_id, guid)


class Cliente:
    def __init__(self, total="100.00"):
        self.total = total
        self.confirmado = False
        self.llamadas = []

    async def autenticar(self):
        self.llamadas.append("autenticar")
        return "token"

    async def obtener_identificador(self, token):
        self.llamadas.append("identificador")
        return "GUID"

    async def mantener_vivo(self, token, guid):
        self.llamadas.append("mantener_vivo")
        return "1"

    async def insertar_item(self, token, **kwargs):
        self.llamadas.append("insertar_item")
        return (
            "<NewDataSet><Table><code>7</code>"
            "<error_description>Insert OK</error_description></Table></NewDataSet>"
        )

    async def obtener_datos_por_guid(self, token, guid):
        self.llamadas.append("obtener_datos_por_guid")
        return (
            "<NewDataSet><Table><item_id>1</item_id><item_code>A</item_code>"
            "<item_desc>Articulo A</item_desc><tis_qty>1</tis_qty>"
            "<tis_price>82.644628</tis_price><stor_id>18</stor_id></Table></NewDataSet>"
        )

    async def obtener_totales(self, token, **kwargs):
        self.llamadas.append("obtener_totales")
        return (
            "<NewDataSet><Table><ErrorCode>0</ErrorCode>"
            f"<Total>{self.total}</Total></Table></NewDataSet>"
        )

    async def confirmar_pedido(self, token, **kwargs):
        self.llamadas.append("confirmar_pedido")
        self.confirmado = True
        return "<NewDataSet><Table><soh_id>999</soh_id></Table></NewDataSet>"


def configuracion(**overrides):
    valores = {
        "_env_file": None,
        "dry_run": False,
        "pedidos_escritura_gbp_habilitada": True,
        "pedidos_gbp_confirmation_enabled": True,
        "pedidos_gbp_staging_enabled": True,
    }
    valores.update(overrides)
    return ConfiguracionAplicacion(**valores)


@pytest.mark.asyncio
async def test_confirmacion_bloqueada_por_defecto():
    cfg = ConfiguracionAplicacion(
        _env_file=None,
        dry_run=False,
        pedidos_escritura_gbp_habilitada=False,
        pedidos_gbp_staging_enabled=False,
        pedidos_gbp_confirmation_enabled=False,
    )
    with pytest.raises(ConfirmacionPedidoGBPDeshabilitadaError):
        await ConfirmarPedidoGBP(Preparador(), Cliente(), Repositorio(), cfg).ejecutar(
            1
        )


@pytest.mark.asyncio
async def test_confirma_y_persiste_soh_id():
    repo = Repositorio()
    cliente = Cliente()
    resultado = await ConfirmarPedidoGBP(
        Preparador(), cliente, repo, configuracion()
    ).ejecutar(1)

    assert resultado["gbp_order_id"] == "999"
    assert repo.guardado == (1, "999", "GUID")
    assert cliente.confirmado
    assert cliente.llamadas == [
        "autenticar",
        "identificador",
        "insertar_item",
        "mantener_vivo",
        "obtener_datos_por_guid",
        "obtener_totales",
        "autenticar",
        "mantener_vivo",
        "confirmar_pedido",
    ]


@pytest.mark.asyncio
async def test_idempotencia_evitar_nueva_escritura():
    cliente = Cliente()
    resultado = await ConfirmarPedidoGBP(
        Preparador(), cliente, Repositorio("888"), configuracion()
    ).ejecutar(1)

    assert resultado["codigo"] == "PEDIDO_GBP_YA_CONFIRMADO"
    assert cliente.llamadas == []


@pytest.mark.asyncio
async def test_no_confirma_si_total_no_concilia():
    cliente = Cliente("99.00")
    with pytest.raises(PedidoGBPNoConciliadoError):
        await ConfirmarPedidoGBP(
            Preparador(), cliente, Repositorio(), configuracion()
        ).ejecutar(1)
    assert not cliente.confirmado


@pytest.mark.asyncio
async def test_bloquea_confirmacion_concurrente():
    from app.aplicacion.pedidos.casos_uso.confirmar_pedido_gbp import (
        ConfirmacionPedidoGBPEnCursoError,
    )

    repo = Repositorio()
    repo.en_curso = True
    cliente = Cliente()
    with pytest.raises(ConfirmacionPedidoGBPEnCursoError):
        await ConfirmarPedidoGBP(Preparador(), cliente, repo, configuracion()).ejecutar(
            1
        )
    assert cliente.llamadas == []
