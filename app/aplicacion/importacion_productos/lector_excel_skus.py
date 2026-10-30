"""Lectura restringida de SKU desde XLSX (OOXML), sin ejecutar macros ni fórmulas."""
from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

MAX_BYTES = 2_000_000
MAX_ROWS = 500
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG = '{http://schemas.openxmlformats.org/package/2006/relationships}'
SKU_RE = re.compile(r'^[\w.\-/]{1,80}$', re.UNICODE)


class ExcelSKUError(ValueError):
    """Archivo o lista de SKU inválidos."""


def leer_skus_xlsx(contenido: bytes) -> dict[str, object]:
    if not contenido or len(contenido) > MAX_BYTES:
        raise ExcelSKUError('El archivo debe tener entre 1 byte y 2 MB.')
    try:
        with ZipFile(BytesIO(contenido)) as archive:
            names = set(archive.namelist())
            if 'xl/workbook.xml' not in names or 'xl/_rels/workbook.xml.rels' not in names:
                raise ExcelSKUError('No es un archivo XLSX válido.')
            for name in names:
                meta = archive.getinfo(name)
                if meta.file_size > 4_000_000 or meta.compress_size and meta.file_size / meta.compress_size > 100:
                    raise ExcelSKUError('El XLSX excede los límites de seguridad.')
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            sheets = workbook.find(f'{NS}sheets')
            if sheets is None or not len(sheets):
                raise ExcelSKUError('El libro no contiene hojas.')
            rid = sheets[0].attrib.get(f'{REL}id')
            relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            target = next((rel.attrib.get('Target') for rel in relationships if rel.attrib.get('Id') == rid), None)
            if not target:
                raise ExcelSKUError('No se encontró la primera hoja.')
            path = ('xl/' + target.lstrip('/')) if not target.startswith('/xl/') and not target.startswith('xl/') else target.lstrip('/')
            path = str(PurePosixPath(path))
            if path not in names or '..' in PurePosixPath(path).parts:
                raise ExcelSKUError('La hoja del Excel es inválida.')
            strings: list[str] = []
            if 'xl/sharedStrings.xml' in names:
                shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                strings = [''.join(t.text or '' for t in si.iter(f'{NS}t')) for si in shared]
            sheet = ET.fromstring(archive.read(path))
            data = sheet.find(f'{NS}sheetData')
            if data is None:
                raise ExcelSKUError('La hoja está vacía.')
            valores = []
            for row in data.findall(f'{NS}row'):
                if len(valores) > MAX_ROWS:
                    raise ExcelSKUError(f'Máximo {MAX_ROWS} SKU por archivo.')
                first = next((cell for cell in row.findall(f'{NS}c') if re.match(r'^A\d+$', cell.attrib.get('r', ''))), None)
                if first is None:
                    valores.append('')
                    continue
                typ = first.attrib.get('t')
                raw = first.findtext(f'{NS}v', default='')
                if typ == 's':
                    try:
                        raw = strings[int(raw)]
                    except (IndexError, ValueError):
                        raise ExcelSKUError('Cadena compartida inválida.') from None
                elif typ == 'inlineStr':
                    raw = ''.join(t.text or '' for t in first.iter(f'{NS}t'))
                elif first.find(f'{NS}f') is not None:
                    raise ExcelSKUError('No se permiten fórmulas en la columna SKU.')
                valores.append(raw.strip())
    except (BadZipFile, ET.ParseError, KeyError, OSError) as exc:
        raise ExcelSKUError('No se pudo leer el archivo XLSX.') from exc
    if not valores or valores[0].casefold() != 'sku':
        raise ExcelSKUError('La celda A1 debe contener el encabezado SKU.')
    if len(valores) - 1 > MAX_ROWS:
        raise ExcelSKUError(f'Máximo {MAX_ROWS} SKU por archivo.')
    skus: list[str] = []
    duplicados: list[str] = []
    invalidos: list[int] = []
    vistos: set[str] = set()
    for numero, sku in enumerate(valores[1:], start=2):
        if not sku:
            continue
        if not SKU_RE.fullmatch(sku):
            invalidos.append(numero)
            continue
        clave = sku.casefold()
        if clave in vistos:
            duplicados.append(sku)
            continue
        vistos.add(clave)
        skus.append(sku)
    if invalidos:
        raise ExcelSKUError('SKU inválido en fila(s): ' + ', '.join(map(str, invalidos[:15])))
    if not skus:
        raise ExcelSKUError('No hay SKU válidos para importar.')
    return {'skus': skus, 'duplicados': duplicados, 'cantidad': len(skus)}
