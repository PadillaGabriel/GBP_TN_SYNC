from app.infraestructura.gbp.clientes import _normalizar_provincia


def test_capital_federal_se_normaliza_como_caba() -> None:
    assert (
        _normalizar_provincia(
            54,
            "Capital Federal",
        )
        == "ciudad autonoma de buenos aires"
    )


def test_caba_se_normaliza_como_ciudad_autonoma() -> None:
    assert (
        _normalizar_provincia(
            54,
            "CABA",
        )
        == "ciudad autonoma de buenos aires"
    )


def test_buenos_aires_no_se_confunde_con_caba() -> None:
    assert (
        _normalizar_provincia(
            54,
            "Buenos Aires",
        )
        == "buenos aires"
    )
