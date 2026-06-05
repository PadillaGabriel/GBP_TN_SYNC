from __future__ import annotations

import html
import re
from xml.etree import ElementTree as ET

from app.domain.errors import DatoIncompletoError


def strip_namespace(tag: str) -> str:
    """Elimina namespace de un tag XML."""

    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_xml_text(text: str) -> str:
    """Sanitiza XML interno devuelto por GBP.

    GBP suele devolver un NewDataSet como texto dentro del SOAP. En catálogos
    grandes puede incluir caracteres inválidos para XML 1.0 o ampersands sin
    escapar. Esta función limpia esos casos sin alterar entidades XML válidas.
    """

    cleaned = (text or "").strip().lstrip("\ufeff")

    if cleaned.startswith("&lt;") or "&lt;NewDataSet" in cleaned[:200]:
        cleaned = html.unescape(cleaned)

    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", cleaned)
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        cleaned,
    )
    return cleaned


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
            row[strip_namespace(child.tag)] = (child.text or "").strip()
        rows.append(row)
    return rows


def get_text_or_none(root: ET.Element, path: str) -> str | None:
    """Extrae texto simple desde un path XML."""

    node = root.find(path)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
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
