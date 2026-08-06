from __future__ import annotations

import re
import unicodedata

from app.infraestructura.gbp.analizador_xml import normalizar_texto_gbp


def normalize_category_key(value: str | None) -> str:
    """Clave canónica para comparar categorías sin duplicar por acento/encoding/caso."""

    text = normalizar_texto_gbp(value)
    text = text.replace("&", " y ")
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    aliases = {
        "bano": "bano",
        "banio": "bano",
        "accesorios bano": "accesorios de bano",
        "accesorios de bano": "accesorios de bano",
        "organizacion": "organizacion",
        "organizacion y orden": "organizacion",
        "cafe te mate": "cafe te y mate",
        "cafe te y mate": "cafe te y mate",
    }
    return aliases.get(text, text)
