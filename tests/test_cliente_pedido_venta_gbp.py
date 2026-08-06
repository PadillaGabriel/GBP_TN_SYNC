from app.infraestructura.gbp.pedidos_venta import ClientePedidoVentaGBP


def test_configuracion_cliente_sale_order():
    cliente = ClientePedidoVentaGBP(
        base_url="https://example.test/wsSaleOrder.asmx",
        username="u",
        password="p",
        company_id="1",
        web_service_id="10",
        branch_id=28,
        language_id=2,
    )
    assert cliente.branch_id == 28
    assert cliente.language_id == 2
