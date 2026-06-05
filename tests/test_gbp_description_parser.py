from app.infrastructure.gbp.xml_parser import parse_dataset_tables


def test_parse_dataset_tables_preserves_description_after_html_tags():
    xml = """
    &lt;NewDataSet&gt;
      &lt;Table&gt;
        &lt;item_code&gt;SKU1&lt;/item_code&gt;
        &lt;WebSite_Description&gt;Titulo&lt;br /&gt;Linea 2&lt;p&gt;Parrafo interno&lt;/p&gt;Final&lt;/WebSite_Description&gt;
      &lt;/Table&gt;
    &lt;/NewDataSet&gt;
    """

    rows = parse_dataset_tables(xml)

    descripcion = rows[0]["WebSite_Description"]
    assert "Titulo" in descripcion
    assert "Linea 2" in descripcion
    assert "Parrafo interno" in descripcion
    assert "Final" in descripcion


def test_parse_dataset_tables_does_not_truncate_long_plain_description():
    cuerpo = "Organizador de Acero Cromado " + ("detalle completo " * 300)
    xml = f"""
    <NewDataSet>
      <Table>
        <item_code>SKU2</item_code>
        <WebSite_Description>{cuerpo}</WebSite_Description>
      </Table>
    </NewDataSet>
    """

    rows = parse_dataset_tables(xml)

    assert rows[0]["WebSite_Description"] == cuerpo.strip()
    assert len(rows[0]["WebSite_Description"]) > 4000
