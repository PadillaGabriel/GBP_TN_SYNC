from io import BytesIO
from zipfile import ZipFile

import pytest

from app.aplicacion.importacion_productos.lector_excel_skus import ExcelSKUError, leer_skus_xlsx


def libro(*values):
    cells = ''.join(
        f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{value}</t></is></c></row>'
        for i, value in enumerate(values, 1)
    )
    workbook = b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    sheet = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{cells}</sheetData></worksheet>'.encode()
    out = BytesIO()
    with ZipFile(out, 'w') as z:
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet)
    return out.getvalue()


def test_lee_sku_deduplica_y_conserva_ceros():
    data = leer_skus_xlsx(libro('SKU', '00123', 'PRD-2', '00123', ''))
    assert data['skus'] == ['00123', 'PRD-2']
    assert data['duplicados'] == ['00123']
    assert data['cantidad'] == 2


def test_rechaza_encabezado_ajeno():
    with pytest.raises(ExcelSKUError, match='A1'):
        leer_skus_xlsx(libro('producto', 'ABC'))


def test_rechaza_sku_no_valido():
    with pytest.raises(ExcelSKUError, match='fila'):
        leer_skus_xlsx(libro('SKU', 'SKU con espacios'))


def test_rechaza_archivo_no_xlsx():
    with pytest.raises(ExcelSKUError):
        leer_skus_xlsx(b'not an xlsx')


def test_rechaza_mas_de_500():
    with pytest.raises(ExcelSKUError, match='500'):
        leer_skus_xlsx(libro('SKU', *(f'A{i}' for i in range(501))))
