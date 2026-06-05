from __future__ import annotations

import html
import re
from xml.etree import ElementTree as ET

from app.domain.errors import DatoIncompletoError


MOJIBAKE_MARKERS = ("Ã", "Â", "�", "", "")

# Secuencias comunes cuando texto UTF-8 fue interpretado como Latin-1/CP1252
# antes de llegar al parser XML. Algunas incluyen caracteres C1 que XML 1.0
# considera inválidos; deben repararse antes de sanear el XML o se pierde
# información, por ejemplo: MUÃECO -> MUÑECO.
MOJIBAKE_SEQUENCES = {
    "Ã": "Á",
    "Ã": "É",
    "Ã": "Í",
    "Ã": "Ó",
    "Ã“": "Ó",
    "Ã": "Ú",
    "Ã": "Ñ",
    "Ã‘": "Ñ",
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã¼": "ü",
    "Â°": "°",
}


def reparar_secuencias_mojibake(value: str) -> str:
    """Repara secuencias de mojibake antes de parsear XML."""

    fixed = value
    for bad, good in MOJIBAKE_SEQUENCES.items():
        fixed = fixed.replace(bad, good)
    return fixed


def strip_namespace(tag: str) -> str:
    """Elimina namespace de un tag XML."""

    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def reparar_mojibake(value: str | None) -> str | None:
    """Corrige texto UTF-8 leído erróneamente como Latin-1/Windows-1252.

    GBP puede devolver contenido con acentos o eñes que llega como mojibake
    después del parseo SOAP/XML. Ejemplos reales: ``DecoraciÃ³n`` y
    ``GenÃ©rica``. La reparación se aplica solo si aparecen marcadores típicos
    para no modificar texto correcto.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        return value
    value = reparar_secuencias_mojibake(value)

    if not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value

    for encoding in ("latin1", "cp1252"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired and repaired != value:
            return repaired
    return value


def normalizar_texto_gbp(value: str | None) -> str:
    """Normaliza texto de GBP para uso interno y publicación."""

    repaired = reparar_mojibake(value)
    if repaired is not None:
        repaired = repaired.replace("\u00ad", "")
    return (repaired or "").strip()


def clean_xml_text(text: str) -> str:
    """Sanitiza XML interno devuelto por GBP.

    GBP suele devolver un NewDataSet como texto dentro del SOAP. En catálogos
    grandes puede incluir caracteres inválidos para XML 1.0 o ampersands sin
    escapar. Esta función limpia esos casos sin alterar entidades XML válidas.
    """

    cleaned = (text or "").strip().lstrip("\ufeff")

    if cleaned.startswith("&lt;") or "&lt;NewDataSet" in cleaned[:200]:
        cleaned = html.unescape(cleaned)

    # Reparar mojibake antes de remover caracteres inválidos XML. Si se
    # elimina primero un C1 como \x91, se pierde la Ñ de secuencias como
    # MUÃ\x91ECO.
    cleaned = reparar_secuencias_mojibake(cleaned)

    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", cleaned)
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        cleaned,
    )
    return cleaned



def decode_gbp_response(content: bytes, fallback_text: str | None = None) -> str:
    """Decodifica respuestas GBP evitando mojibake por charset incorrecto.

    Algunas respuestas llegan como bytes UTF-8 aunque el encabezado o el
    cliente HTTP puedan interpretarlas como Latin-1/CP1252. Priorizar UTF-8
    evita que textos como "Decoración" se transformen en "DecoraciÃ³n" antes
    del parseo.
    """

    if not content:
        return fallback_text or ""

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded:
            return decoded

    return fallback_text or content.decode("utf-8", errors="replace")


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
        root = ET.fromstring(soap_text)
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
