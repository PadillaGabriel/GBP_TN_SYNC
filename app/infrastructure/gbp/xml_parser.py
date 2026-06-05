from xml.etree import ElementTree

from app.domain.errors import DatoIncompletoError


def parse_xml(xml_text: str) -> ElementTree.Element:
    """Parsea XML de GBP de manera controlada."""

    try:
        return ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise DatoIncompletoError("GBP devolvió XML inválido") from exc


def get_text_or_none(root: ElementTree.Element, path: str) -> str | None:
    """Extrae texto simple desde un path XML."""

    node = root.find(path)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None
