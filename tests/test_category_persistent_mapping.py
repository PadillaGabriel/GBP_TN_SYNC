import pytest
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube
from scripts.auditar_categorias_tn import detectar_duplicados


class FakeMapping:
    def __init__(self):
        self.rows = {}

    async def buscar(self, clave, parent):
        return self.rows.get((parent, clave))

    async def guardar(self, clave, parent, category_id):
        self.rows[(parent, clave)] = category_id


@pytest.mark.asyncio
async def test_mapping_only_used_if_remote_name_and_parent_match():
    mapping = FakeMapping()
    mapping.rows[(None, "navidad")] = 8
    adapter = AdaptadorTiendaNube(client=object(), category_mapping=mapping)
    remote = [{"id": 8, "name": {"es": "Otros"}, "parent": None}, {"id": 9, "name": {"es": "Navidad"}, "parent": None}]
    result = await adapter._resolve_persisted_category(remote, name="Navidad", parent_id=None)
    assert result["id"] == 9
    await adapter._remember_category("Navidad", None, 9)
    assert mapping.rows[(None, "navidad")] == 9


def test_dry_run_groups_only_same_parent_and_canonical_name():
    categories = [
        {"id": 10, "name": {"es": "Decoración"}, "parent": None},
        {"id": 11, "name": {"es": "DECORACION"}, "parent": None},
        {"id": 12, "name": {"es": "Decoración"}, "parent": 1},
    ]
    duplicates = detectar_duplicados(categories)
    assert len(duplicates) == 1
    assert duplicates[0]["ids_existentes"] == "10,11"
    assert duplicates[0]["estado"] == "REVISION_MANUAL_OBLIGATORIA"
