import pytest

from app.domain.errors import MetodoNoValidadoError
from app.infrastructure.gbp.module16_registry import Module16Registry


def test_metodo_no_validado_bloquea_en_modo_estricto() -> None:
    registry = Module16Registry(strict=True)

    with pytest.raises(MetodoNoValidadoError):
        registry.validar("obtener_stock")
