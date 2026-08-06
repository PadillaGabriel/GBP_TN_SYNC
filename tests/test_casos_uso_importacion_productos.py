from pathlib import Path


def test_fachada_importacion_delega_en_casos_de_uso() -> None:
    ruta = Path("app/aplicacion/servicios/servicio_importacion_tienda_nube.py")
    contenido = ruta.read_text(encoding="utf-8")
    assert "self._importar_lote.ejecutar" in contenido
    assert "self._importar_manual.ejecutar" in contenido
    assert "self._ocultar_producto.ejecutar" in contenido
    assert "self._eliminar_producto.ejecutar" in contenido
    assert "self._reconciliar_mapeos.ejecutar" in contenido
    assert "self._marcar_eliminados.ejecutar" in contenido


def test_operaciones_estan_separadas_por_funcionalidad() -> None:
    base = Path("app/aplicacion/importacion_productos/casos_uso")
    esperados = {
        "importar_lote_productos.py",
        "importar_producto_manual.py",
        "ocultar_producto.py",
        "eliminar_producto.py",
        "reconciliar_mapeos.py",
        "marcar_eliminados_externos.py",
        "contexto.py",
    }
    assert esperados.issubset({p.name for p in base.glob("*.py")})
