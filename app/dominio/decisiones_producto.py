"""Decisiones normalizadas de publicación de productos."""

PUBLICABLE_AUTOMATICO = "PUBLICABLE_AUTOMATICO"
PUBLICABLE_CONSULTAR_PRECIO = "PUBLICABLE_CONSULTAR_PRECIO"

DECISIONES_PUBLICABLES: tuple[str, ...] = (
    PUBLICABLE_AUTOMATICO,
    PUBLICABLE_CONSULTAR_PRECIO,
)


def es_decision_publicable(decision: str | None) -> bool:
    return str(decision or "") in DECISIONES_PUBLICABLES
