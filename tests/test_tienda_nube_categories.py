from app.dominio.modelos.producto import Producto
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube


class FakeClienteTiendaNube:
    def __init__(self) -> None:
        self.categories = [
            {"id": 1, "name": {"es": "Cocina"}, "parent": None},
        ]
        self.created_categories = []
        self.created_product_payload = None

    async def get_product_by_sku(self, sku: str):
        return None

    async def list_categories(self):
        return list(self.categories)

    async def create_category(self, payload):
        category = {"id": 2, **payload}
        self.categories.append(category)
        self.created_categories.append(payload)
        return category

    async def create_product(self, payload):
        self.created_product_payload = payload
        return {"id": 99, "variants": [{"id": 199}]}

    async def update_product(self, product_id: str, payload):
        raise AssertionError("No deberia actualizar en este test")


async def test_adapter_crea_subcategoria_y_asigna_categorias_al_producto():
    client = FakeClienteTiendaNube()
    adapter = AdaptadorTiendaNube(client=client)
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        categoria_nombre="Cocina",
        subcategoria_nombre="Organizadores",
    )

    resultado = await adapter.crear_o_actualizar_producto(producto)

    assert resultado.exitoso is True
    assert client.created_categories == [{"name": {"es": "Organizadores"}, "parent": 1}]
    assert client.created_product_payload["categories"] == [1, 2]
