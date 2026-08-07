from app.aplicacion.servicios.servicio_sincronizacion_stock import StockSyncService


class FakeTiendaNube:
    def __init__(self, product):
        self.product = product
        self.queries = []

    async def get_product_by_sku(self, sku: str):
        self.queries.append(sku)
        return self.product


class FakeProductosRepo:
    def __init__(self):
        self.reparaciones = []
        self.obsoletos = []

    def reparar_mapeo_tienda_nube(self, **kwargs):
        self.reparaciones.append(kwargs)

    def marcar_mapeo_tienda_nube_obsoleto(self, sku: str):
        self.obsoletos.append(sku)


class FakeAuditoria:
    def __init__(self):
        self.eventos = []

    def registrar(self, **kwargs):
        self.eventos.append(kwargs)


def build_service(product):
    service = StockSyncService.__new__(StockSyncService)
    service.tn = FakeTiendaNube(product)
    service.productos = FakeProductosRepo()
    service.auditoria = FakeAuditoria()
    return service


async def test_repara_mapeo_404_por_sku_y_variante():
    service = build_service(
        {
            "id": 999,
            "variants": [
                {"id": 111, "sku": "OTRO"},
                {"id": 222, "sku": "SKU-1"},
            ],
        }
    )

    result = await service._reparar_vinculacion_tienda_nube(
        sku="SKU-1",
        tn_product_id_anterior="10",
        tn_variant_id_anterior="20",
    )

    assert result == ("999", "222")
    assert service.productos.reparaciones == [
        {"sku": "SKU-1", "tn_product_id": "999", "tn_variant_id": "222"}
    ]
    assert service.productos.obsoletos == []
    assert service.auditoria.eventos[-1]["estado"] == "MAPEO_TN_REPARADO"


async def test_marca_obsoleto_si_sku_ya_no_existe():
    service = build_service(None)

    result = await service._reparar_vinculacion_tienda_nube(
        sku="SKU-2",
        tn_product_id_anterior="10",
        tn_variant_id_anterior="20",
    )

    assert result is None
    assert service.productos.reparaciones == []
    assert service.productos.obsoletos == ["SKU-2"]
    assert service.auditoria.eventos[-1]["estado"] == "MAPEO_TN_OBSOLETO"


async def test_no_inventa_variante_si_hay_varias_y_ninguna_coincide():
    service = build_service(
        {
            "id": 999,
            "variants": [
                {"id": 111, "sku": "A"},
                {"id": 222, "sku": "B"},
            ],
        }
    )

    result = await service._reparar_vinculacion_tienda_nube(
        sku="SKU-3",
        tn_product_id_anterior="10",
        tn_variant_id_anterior="20",
    )

    assert result is None
    assert service.productos.obsoletos == ["SKU-3"]


def test_resumen_distingue_mapeos_reparados_y_obsoletos():
    service = StockSyncService.__new__(StockSyncService)
    resumen = {
        "procesados": 0,
        "actualizados": 0,
        "simulados": 0,
        "sin_cambios": 0,
        "stock_no_consultable": 0,
        "mapeos_reparados": 0,
        "mapeos_obsoletos": 0,
        "errores": 0,
    }

    service._sumar_resultado(resumen, {"estado": "ACTUALIZADO_MAPEO_REPARADO"})
    service._sumar_resultado(resumen, {"estado": "MAPEO_TN_OBSOLETO"})

    assert resumen["procesados"] == 2
    assert resumen["actualizados"] == 1
    assert resumen["mapeos_reparados"] == 1
    assert resumen["mapeos_obsoletos"] == 1
    assert resumen["errores"] == 0
