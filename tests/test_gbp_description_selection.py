from app.infraestructura.gbp.normalizador import GBPNormalizer
from app.infraestructura.gbp.analizador_xml import parse_dataset_tables


def _base_row(**extra):
    return {
        "item_code": "SKU",
        "item_id": "1",
        "item_desc": "Producto",
        "item_web": "true",
        "item_disabled": "false",
        "item_not4Sale": "false",
        **extra,
    }


def test_normalizer_uses_longest_web_description_candidate():
    data = _base_row(
        WebSite_Description="SOMOS SILMAR BAZAR ONLINE\n•Realizamos envíos",
        item_WebDescriptionFull=(
            "SOMOS SILMAR BAZAR ONLINE\n\n"
            "•Realizamos envíos a todo el pais\n\n"
            "============================================================\n"
            "DISPENSER JABON LIQUIDO DE CERAMICA\n"
            "•Art 6130\n"
            "•Material: Cerámica con dosificador plástico simil metal\n"
        ),
    )

    producto = GBPNormalizer().normalizar_producto(data)

    assert "DISPENSER JABON LIQUIDO DE CERAMICA" in producto.descripcion_web
    assert "Cerámica con dosificador" in producto.descripcion_web
    assert len(producto.descripcion_web) > len(data["WebSite_Description"])


def test_normalizer_does_not_use_item_detail_as_web_description_candidate():
    data = _base_row(
        WebSite_Description="Descripción web corta válida",
        item_detail="Texto largo de rubro interno que no debe publicarse " * 20,
    )

    producto = GBPNormalizer().normalizar_producto(data)

    assert producto.descripcion_web == "Descripción web corta válida"


def test_parse_dataset_tables_concatenates_duplicate_description_nodes():
    xml = """
    <NewDataSet>
      <Table>
        <item_code>SKU</item_code>
        <WebSite_Description>Primera parte</WebSite_Description>
        <WebSite_Description>Segunda parte</WebSite_Description>
      </Table>
    </NewDataSet>
    """

    rows = parse_dataset_tables(xml)

    assert rows[0]["WebSite_Description"] == "Primera parte\nSegunda parte"


def test_normalizer_uses_item_detail_only_when_it_extends_web_description_prefix():
    short = "SOMOS SILMAR BAZAR ONLINE\n\n•Realizamos envíos a todo el pais, podes ver la fecha de entrega estimada"
    full = (
        short
        + " presionando donde dice ver más formas de entrega.\n\nDISPENSER JABON LIQUIDO DE CERAMICA\n•Art 6130"
    )
    data = _base_row(
        WebSite_Description=short,
        item_detail=full,
    )

    producto = GBPNormalizer().normalizar_producto(data)

    assert producto.descripcion_web == full
    assert "DISPENSER JABON LIQUIDO DE CERAMICA" in producto.descripcion_web
