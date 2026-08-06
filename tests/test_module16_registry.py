import pytest

from app.dominio.errores import MetodoNoValidadoError
from app.infraestructura.gbp.registro_modulo16 import RegistroModulo16


def test_metodo_no_validado_bloquea_en_modo_estricto() -> None:
    registry = RegistroModulo16(strict=True)

    with pytest.raises(MetodoNoValidadoError):
        registry.validar("obtener_stock")
