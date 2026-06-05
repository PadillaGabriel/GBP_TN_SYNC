from app.infrastructure.gbp.normalizer import GBPNormalizer
from app.infrastructure.gbp.xml_parser import parse_dataset_tables, reparar_mojibake


def test_reparar_mojibake_corrige_acentos_y_enie() -> None:
    assert reparar_mojibake("DecoraciÃ³n GenÃ©rica MUÃ‘ECO") == "Decoración Genérica MUÑECO"


def test_parse_dataset_tables_repara_textos_gbp() -> None:
    xml = """
    <NewDataSet>
      <Table>
        <item_desc>FAROL C/PIE NIEVE MUÃ‘ECO PATIN</item_desc>
        <subcat_desc>Adornos y DecoraciÃ³n</subcat_desc>
        <brand_desc>02 - GenÃ©rica</brand_desc>
      </Table>
    </NewDataSet>
    """

    row = parse_dataset_tables(xml)[0]

    assert row["item_desc"] == "FAROL C/PIE NIEVE MUÑECO PATIN"
    assert row["subcat_desc"] == "Adornos y Decoración"
    assert row["brand_desc"] == "02 - Genérica"


def test_normalizador_producto_repara_textos() -> None:
    normalizer = GBPNormalizer()

    producto = normalizer.normalizar_producto(
        {
            "item_id": 32,
            "item_code": "1658",
            "item_desc": "ORGANIZADOR MET/MADERA X3 CAÃ‘A",
            "cat_desc": "Cocina",
            "subcat_desc": "Organizadores de cocina",
            "brand_desc": "02 - GenÃ©rica",
            "item_web": "true",
            "WebSite_Description": "DescripciÃ³n web",
        }
    )

    assert producto.titulo == "ORGANIZADOR MET/MADERA X3 CAÑA"
    assert producto.marca_nombre == "02 - Genérica"
    assert producto.descripcion_web == "Descripción web"
