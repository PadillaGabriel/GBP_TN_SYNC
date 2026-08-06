from pathlib import Path


def test_casos_uso_no_dependen_de_infraestructura() -> None:
    raiz = Path(__file__).resolve().parents[1] / "app" / "aplicacion" / "casos_uso"
    infracciones: list[str] = []
    for archivo in raiz.glob("*.py"):
        contenido = archivo.read_text(encoding="utf-8")
        if "app.infraestructura" in contenido:
            infracciones.append(archivo.name)
    assert not infracciones, f"Casos de uso acoplados a infraestructura: {infracciones}"


def test_repositorios_estan_separados_por_responsabilidad() -> None:
    raiz = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "infraestructura"
        / "persistencia"
        / "repositorios"
    )
    esperados = {
        "productos.py",
        "depositos.py",
        "auditoria_sincronizacion.py",
        "trabajos_sincronizacion.py",
    }
    assert esperados.issubset({archivo.name for archivo in raiz.glob("*.py")})
