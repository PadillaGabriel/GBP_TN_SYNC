from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.repositorios.categorias import (
    RepositorioNormalizacionCategorias,
)
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube


class _Client:
    def __init__(self):
        self.categories = [{"id": 10, "name": {"es": "Cocina"}, "parent": None}]
        self.created = []

    async def list_categories(self):
        return list(self.categories)

    async def create_category(self, payload):
        created = {"id": 20 + len(self.created), **payload}
        self.created.append(payload)
        self.categories.append(created)
        return created


def test_repositorio_resuelve_alias_comercial_y_contexto_subcategoria():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        repo = RepositorioNormalizacionCategorias(db)
        repo.guardar(
            tipo="categoria",
            valor_origen="COCINAS Y ACCESORIOS",
            valor_canonico="Cocina",
        )
        repo.guardar(
            tipo="subcategoria",
            valor_origen="ORGANIZACION Y ORDEN",
            valor_canonico="Organización",
            categoria_padre_canonica="Cocina",
        )
        assert repo.resolver("categoria", "cocinas y accesorios") == "Cocina"
        assert (
            repo.resolver("subcategoria", "Organización y orden", "Cocina")
            == "Organización"
        )
        assert repo.resolver("categoria", "Mesa") == "Mesa"


def test_adapter_aplica_resolver_antes_de_crear_categoria():
    client = _Client()

    def resolver(tipo, valor, padre):
        if tipo == "categoria" and valor == "COCINAS":
            return "Cocina"
        return valor

    adapter = AdaptadorTiendaNube(client=client, category_name_resolver=resolver)
    assert adapter._resolve_category_name("categoria", "COCINAS", None) == "Cocina"
