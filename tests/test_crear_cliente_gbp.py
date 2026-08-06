import pytest

from app.aplicacion.pedidos.casos_uso.crear_cliente_gbp import (
    AltaClienteGBPError,
    CrearClienteGBP,
    DatosClienteGBPInvalidosError,
    EscrituraClienteGBPDeshabilitadaError,
    PedidoNoEncontradoParaAltaClienteError,
)
from app.configuracion import ConfiguracionAplicacion


class RepositorioFalso:
    def __init__(self, documento="33.214.438", email="MELISA@EXAMPLE.COM"):
        self.documento = documento
        self.email = email
        self.vinculado = None

    def obtener_por_id_para_validacion(self, pedido_id):
        if pedido_id == 404:
            return None
        return {
            "id": pedido_id,
            "correlation_id": "corr-1",
            "cliente": {
                "nombre": " Melisa  Elena ",
                "apellido": " Carmona ",
                "numero_documento": self.documento,
                "email": self.email,
                "telefono": "+542964610324",
                "tipo_documento": "DNI",
            },
            "envio": {
                "direccion": "Laguna Don Bosco 1636",
                "ciudad": "Río Grande",
                "provincia": "Tierra del Fuego",
                "codigo_postal": "9420",
                "pais": "ar",
            },
        }

    def vincular_cliente_gbp(self, pedido_id, cust_id):
        self.vinculado = (pedido_id, cust_id)


class ClienteGBPFalso:
    def __init__(self, existentes=None, posteriores=None, creado=56369):
        self.existentes = existentes or []
        self.posteriores = posteriores
        self.creado = creado
        self.busquedas = 0
        self.alta = None

    async def buscar_por_documento(self, documento):
        self.busquedas += 1
        if self.busquedas > 1 and self.posteriores is not None:
            return self.posteriores
        return self.existentes

    async def resolver_provincia(self, *, country_id, provincia):
        assert country_id == 54
        assert provincia == "Tierra del Fuego"
        return 54018

    async def crear_cliente(self, **kwargs):
        self.alta = kwargs
        return self.creado


def configuracion(**cambios):
    return ConfiguracionAplicacion(
        _env_file=None,
        dry_run=cambios.get("dry_run", True),
        pedidos_escritura_gbp_habilitada=cambios.get("escritura", False),
    )


@pytest.mark.asyncio
async def test_simula_alta_y_normaliza_payload() -> None:
    resultado = await CrearClienteGBP(
        RepositorioFalso(), ClienteGBPFalso(), configuracion()
    ).ejecutar(1)

    assert resultado["codigo"] == "CLIENTE_GBP_ALTA_SIMULADA"
    assert resultado["modo"] == "SIMULACION"
    assert resultado["plan"]["state_id"] == 54018
    assert resultado["plan"]["fiscal_class_id"] == 2
    assert resultado["plan"]["tax_number_type_id"] == 5
    assert resultado["plan"]["customer"]["city"] == "Rio Grande"


@pytest.mark.asyncio
async def test_bloquea_escritura_si_flag_desactivado() -> None:
    with pytest.raises(EscrituraClienteGBPDeshabilitadaError):
        await CrearClienteGBP(
            RepositorioFalso(),
            ClienteGBPFalso(),
            configuracion(dry_run=False, escritura=False),
        ).ejecutar(1)


@pytest.mark.asyncio
async def test_devuelve_cliente_existente_sin_duplicar() -> None:
    repo = RepositorioFalso()
    resultado = await CrearClienteGBP(
        repo,
        ClienteGBPFalso(existentes=[{"cust_id": "56369"}]),
        configuracion(dry_run=False, escritura=True),
    ).ejecutar(1)

    assert resultado["codigo"] == "CLIENTE_GBP_YA_EXISTE"
    assert resultado["cust_id"] == 56369
    assert repo.vinculado == (1, 56369)


@pytest.mark.asyncio
async def test_crea_verifica_y_vincula_cliente() -> None:
    repo = RepositorioFalso()
    cliente = ClienteGBPFalso(posteriores=[{"cust_id": "56369"}])
    resultado = await CrearClienteGBP(
        repo, cliente, configuracion(dry_run=False, escritura=True)
    ).ejecutar(1)

    assert resultado["codigo"] == "CLIENTE_GBP_CREADO"
    assert resultado["cust_id"] == 56369
    assert cliente.alta["ciudad"] == "Río Grande"
    assert cliente.alta["fiscal_class_id"] == 2
    assert cliente.alta["tax_number_type_id"] == 5
    assert repo.vinculado == (1, 56369)


@pytest.mark.asyncio
async def test_rechaza_verificacion_ambigua() -> None:
    with pytest.raises(AltaClienteGBPError, match="ALTA_NO_VERIFICADA"):
        await CrearClienteGBP(
            RepositorioFalso(),
            ClienteGBPFalso(posteriores=[]),
            configuracion(dry_run=False, escritura=True),
        ).ejecutar(1)


@pytest.mark.asyncio
async def test_rechaza_documento_invalido() -> None:
    with pytest.raises(
        DatosClienteGBPInvalidosError, match="CLIENTE_DOCUMENTO_FORMATO_INVALIDO"
    ):
        await CrearClienteGBP(
            RepositorioFalso(documento="123"), ClienteGBPFalso(), configuracion()
        ).ejecutar(1)


@pytest.mark.asyncio
async def test_rechaza_email_ausente() -> None:
    with pytest.raises(DatosClienteGBPInvalidosError, match="CLIENTE_EMAIL_REQUERIDO"):
        await CrearClienteGBP(
            RepositorioFalso(email=None), ClienteGBPFalso(), configuracion()
        ).ejecutar(1)


@pytest.mark.asyncio
async def test_pedido_inexistente() -> None:
    with pytest.raises(PedidoNoEncontradoParaAltaClienteError):
        await CrearClienteGBP(
            RepositorioFalso(), ClienteGBPFalso(), configuracion()
        ).ejecutar(404)
