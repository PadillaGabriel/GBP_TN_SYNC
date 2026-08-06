from __future__ import annotations


def extraer_id_producto_tn(producto_tn: object) -> str | None:
    """Obtiene el identificador de producto desde una respuesta de Tienda Nube."""

    if isinstance(producto_tn, dict):
        valor = producto_tn.get("id")
        return str(valor) if valor not in (None, "") else None
    return None


def extraer_id_variante_tn(producto_tn: object) -> str | None:
    """Obtiene el identificador de la primera variante de Tienda Nube."""

    if not isinstance(producto_tn, dict):
        return None
    variantes = producto_tn.get("variants") or []
    if not variantes or not isinstance(variantes, list):
        return None
    primera = variantes[0]
    if not isinstance(primera, dict):
        return None
    valor = primera.get("id")
    return str(valor) if valor not in (None, "") else None
