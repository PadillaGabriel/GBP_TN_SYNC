from __future__ import annotations

import html
import re
from xml.etree import ElementTree as ET

from app.domain.errors import DatoIncompletoError


# Marcadores típicos de UTF-8 leído como Latin-1/CP1252.
MOJIBAKE_MARKERS = ("Ã", "Â", "�", "\x91", "\x93", "\x8d", "\x9a")

# Secuencias completas que deben repararse antes de limpiar XML inválido.
# Algunas contienen caracteres C1 que XML 1.0 no acepta. Si se eliminan antes,
# se pierde información: MUÃ\x91ECO -> MUÃECO.
MOJIBAKE_SEQUENCES = {
    "Ã\x81": "Á",
    "Ã\x89": "É",
    "Ã\x8d": "Í",
    "Ã\x93": "Ó",
    "Ã\x9a": "Ú",
    "Ã\x91": "Ñ",
    "ÃÁ": "Á",
    "ÃÉ": "É",
    "ÃÍ": "Í",
    "ÃÓ": "Ó",
    "ÃÚ": "Ú",
    "Ã": "Ñ",
    "Ã“": "Ó",
    "Ã¡": "á",
    "Ã©": "é",
    "Ã\xad": "í",
    "Ãí": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã¼": "ü",
    "Â°": "°",
    "Âº": "º",
    "Âª": "ª",
}

# Casos ya dañados por haber perdido un byte/caracter C1 antes de llegar acá.
# No se usan como regla general de idioma; son patrones reales observados en GBP.
DAMAGED_SEQUENCES = {
    "MUÃECO": "MUÑECO",
    "MuÃeco": "Muñeco",
    "muÃeco": "muñeco",
    "categorÃa": "categoría",
    "CategorÃa": "Categoría",
    "CATEGORÃA": "CATEGORÍA",
}


def reparar_secuencias_mojibake(value: str) -> str:
    """Repara secuencias de mojibake antes de parsear XML."""

    fixed = value
    for bad, good in MOJIBAKE_SEQUENCES.items():
        fixed = fixed.replace(bad, good)
    for bad, good in DAMAGED_SEQUENCES.items():
        fixed = fixed.replace(bad, good)
    return fixed


def strip_namespace(tag: str) -> str:
    """Elimina namespace de un tag XML."""

    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def reparar_mojibake(value: str | None) -> str | None:
    """Corrige texto UTF-8 leído erróneamente como Latin-1/Windows-1252."""

    if value is None:
        return None
    if not isinstance(value, str):
        return value

    text = reparar_secuencias_mojibake(value)

    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text

    # Reparación por re-interpretación. Solo se acepta si reduce mojibake.
    original_marker_count = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(encoding, errors="strict").decode("utf-8", errors="strict")
        except UnicodeError:
            continue
        repaired = reparar_secuencias_mojibake(repaired)
        repaired_marker_count = sum(repaired.count(marker) for marker in MOJIBAKE_MARKERS)
        if repaired and repaired != text and repaired_marker_count < original_marker_count:
            return repaired

    return text


def normalizar_texto_gbp(value: str | None) -> str:
    """Normaliza texto de GBP para uso interno y publicación."""

    repaired = reparar_mojibake(value)
    if repaired is not None:
        repaired = repaired.replace("\u00ad", "")
    return (repaired or "").strip()


def clean_xml_text(text: str) -> str:
    """Sanitiza XML interno devuelto por GBP.

    GBP devuelve NewDataSet como texto dentro del SOAP. En catálogos grandes
    puede traer caracteres inválidos para XML 1.0 o ampersands crudos.
    """

    cleaned = (text or "").strip().lstrip("\ufeff")

    if cleaned.startswith("&lt;") or "&lt;NewDataSet" in cleaned[:300]:
        cleaned = html.unescape(cleaned)

    # Reparar antes de eliminar caracteres inválidos.
    cleaned = reparar_secuencias_mojibake(cleaned)

    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", cleaned)
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        cleaned,
    )
    return cleaned


def decode_gbp_response(content: bytes, fallback_text: str | None = None) -> str:
    """Decodifica respuestas GBP evitando charset incorrecto de httpx."""

    if not content:
        return fallback_text or ""

    candidates: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded:
            candidates.append(decoded)

    if fallback_text:
        candidates.append(fallback_text)

    if not candidates:
        return content.decode("utf-8", errors="replace")

    # Elegir la variante con menos marcadores de mojibake tras reparación simple.
    def score(value: str) -> tuple[int, int]:
        repaired = reparar_secuencias_mojibake(value)
        marker_count = sum(repaired.count(marker) for marker in MOJIBAKE_MARKERS)
        replacement_count = repaired.count("�")
        return marker_count + replacement_count, len(repaired)

    best = min(candidates, key=score)
    return reparar_secuencias_mojibake(best)


def normalizar_objeto_gbp(value):
    """Normaliza recursivamente textos GBP en dict/list para respuestas JSON."""

    if isinstance(value, str):
        return normalizar_texto_gbp(value)
    if isinstance(value, list):
        return [normalizar_objeto_gbp(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalizar_objeto_gbp(item) for item in value)
    if isinstance(value, dict):
        return {key: normalizar_objeto_gbp(item) for key, item in value.items()}
    return value


def parse_xml(xml_text: str) -> ET.Element:
    """Parsea XML de GBP de manera controlada."""

    try:
        return ET.fromstring(clean_xml_text(xml_text))
    except ET.ParseError as exc:
        raise DatoIncompletoError(f"GBP devolvió XML inválido: {exc}") from exc


def extract_result_text(soap_text: str, method_name: str) -> str:
    """Extrae el texto del nodo *Result de una respuesta SOAP."""

    try:
        root = ET.fromstring(clean_xml_text(soap_text))
    except ET.ParseError as exc:
        raise DatoIncompletoError(f"GBP devolvió SOAP inválido: {exc}") from exc

    expected = f"{method_name}Result"
    for node in root.iter():
        if strip_namespace(node.tag) == expected:
            return node.text or ""

    for node in root.iter():
        if strip_namespace(node.tag).endswith("Result"):
            return node.text or ""

    return ""


def parse_dataset_tables(result_text: str) -> list[dict[str, str]]:
    """Convierte un NewDataSet XML en lista de filas dict."""

    cleaned = clean_xml_text(result_text)
    if not cleaned or cleaned.lower() == "not data found.":
        return []

    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise DatoIncompletoError(f"No se pudo parsear XML interno GBP: {exc}") from exc

    rows: list[dict[str, str]] = []
    for table in root.iter():
        if strip_namespace(table.tag) != "Table":
            continue
        row: dict[str, str] = {}
        for child in list(table):
            row[strip_namespace(child.tag)] = normalizar_texto_gbp(child.text)
        rows.append(row)
    return rows


def get_text_or_none(root: ET.Element, path: str) -> str | None:
    """Extrae texto simple desde un path XML."""

    node = root.find(path)
    if node is None or node.text is None:
        return None
    value = normalizar_texto_gbp(node.text)
    return value or None


def has_value(value: object) -> bool:
    """Indica si un valor tiene contenido real."""

    return bool(str(value or "").strip())


def any_website_image(row: dict[str, str]) -> bool:
    """Detecta si hay al menos una imagen Website cargada."""

    return any(has_value(row.get(f"item_WebSite_url4Image{index}")) for index in range(1, 11))


def to_bool(value: object) -> bool:
    """Convierte booleano textual GBP a bool."""

    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "si", "sí"}


def to_bool_or_none(value: object) -> bool | None:
    """Convierte booleano textual GBP preservando vacío como None."""

    if value is None or str(value).strip() == "":
        return None
    return to_bool(value)
