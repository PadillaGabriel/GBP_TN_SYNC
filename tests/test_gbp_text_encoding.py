from app.infrastructure.gbp.normalizer import GBPNormalizer
from app.infrastructure.gbp.xml_parser import normalizar_texto_gbp, parse_dataset_tables, reparar_mojibake


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


def test_repara_mojibake_con_caracter_c1_antes_de_xml():
    assert normalizar_texto_gbp("MUÃ\x91ECO") == "MUÑECO"
    assert normalizar_texto_gbp("Sin categorÃ\xad­a") in {"Sin categoría", "Sin categoría"}


def test_clean_xml_repara_mojibake_antes_de_remover_invalidos():
    from app.infrastructure.gbp.xml_parser import parse_dataset_tables

    xml = "<NewDataSet><Table><item_desc>MUÃ\x91ECO</item_desc><cat_desc>DecoraciÃ³n</cat_desc></Table></NewDataSet>"
    rows = parse_dataset_tables(xml)
    assert rows[0]["item_desc"] == "MUÑECO"
    assert rows[0]["cat_desc"] == "Decoración"


def test_decode_gbp_response_prefiere_utf8() -> None:
    from app.infrastructure.gbp.xml_parser import decode_gbp_response

    content = "Decoración Genérica MUÑECO".encode("utf-8")

    assert decode_gbp_response(content) == "Decoración Genérica MUÑECO"


def test_normalizar_objeto_gbp_recursivo() -> None:
    from app.infrastructure.gbp.xml_parser import normalizar_objeto_gbp

    data = {
        "titulo": "MUÃ‘ECO",
        "categoria": "DecoraciÃ³n",
        "items": [{"marca": "GenÃ©rica"}],
    }

    assert normalizar_objeto_gbp(data) == {
        "titulo": "MUÑECO",
        "categoria": "Decoración",
        "items": [{"marca": "Genérica"}],
    }


def test_normalizar_texto_gbp_corrige_bullet_y_acentos_descripcion_larga() -> None:
    text = (
        "SOMOS SILMAR BAZAR ONLINE\n\n"
        "â¢Realizamos envÃos a todo el pais, podes ver la fecha de entrega estimada\n"
        "presionando donde dice ver mÃ¡s formas de entrega y colocando tu cÃ³digo postal.\n\n"
        "â¢Si estas en CABA o GBA, tu pedido llega en el dÃa comprando antes de las 14hs.\n"
        "â¢Material: CerÃ¡mica con dosificador plÃ¡stico simil metal\n"
        "â¢Dispenser para jabÃ³n liquido o detergente\n"
        "â¢LanÃºs Oeste."
    )

    fixed = normalizar_texto_gbp(text)

    assert "•Realizamos envíos" in fixed
    assert "más formas" in fixed
    assert "código postal" in fixed
    assert "día comprando" in fixed
    assert "Cerámica" in fixed
    assert "plástico" in fixed
    assert "jabón" in fixed
    assert "Lanús Oeste" in fixed
    assert "â" not in fixed
    assert "Ã" not in fixed
