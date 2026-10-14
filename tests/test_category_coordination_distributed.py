import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube
from app.infraestructura.tienda_nube.coordinacion_categorias import CoordinadorCategoriasPostgres
from app.dominio.modelos.producto import Producto


class FakeCoordinator:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.acquisitions = 0

    @asynccontextmanager
    async def proteger(self):
        async with self.lock:
            self.acquisitions += 1
            yield


class FakeStore:
    def __init__(self):
        self.categories = []
        self.next_id = 1

    async def list_categories(self):
        await asyncio.sleep(0)
        return [dict(cat) for cat in self.categories]

    async def create_category(self, payload):
        await asyncio.sleep(0)
        new = {"id": self.next_id, **payload}
        self.next_id += 1
        self.categories.append(new)
        return new


@pytest.mark.asyncio
async def test_multi_adapter_creation_coordinated_without_duplicates():
    store, coordinator = FakeStore(), FakeCoordinator()
    adapters = [AdaptadorTiendaNube(client=store, category_coordinator=coordinator) for _ in range(2)]
    products = [Producto(sku=str(n), id_sistema_gbp=str(n), titulo="Producto",
                         categoria_nombre="Cocina", subcategoria_nombre="Organizadores") for n in range(2)]
    results = await asyncio.gather(*(adapter._ensure_category_tree(prod)
                                     for adapter, prod in zip(adapters, products)))
    assert results == [[1, 2], [1, 2]]
    assert len(store.categories) == 2
    assert coordinator.acquisitions == 2


def test_distributed_lock_is_stable_and_per_store():
    one = CoordinadorCategoriasPostgres(database_url="postgresql://user:pass@localhost/db", store_id="123")
    same = CoordinadorCategoriasPostgres(database_url="postgresql+psycopg://user:pass@localhost/db", store_id="123")
    other = CoordinadorCategoriasPostgres(database_url="postgresql://user:pass@localhost/db", store_id="456")
    assert one._lock_id == same._lock_id
    assert one._lock_id != other._lock_id


@pytest.mark.asyncio
async def test_category_listing_refuses_incomplete_catalog(monkeypatch):
    client = ClienteTiendaNube(base_url="https://example.test", store_id="123", access_token="t", timeout_seconds=3)
    requests = []

    async def fake_request(self, session, method, url, **kwargs):
        requests.append(kwargs["params"]["page"])
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, json=[{"id": len(requests), "name": {"es": "Duplicado"}}])

    monkeypatch.setattr(ClienteTiendaNube, "_request_with_retries", fake_request)
    with pytest.raises(RuntimeError, match="límite de paginación"):
        await client.list_categories(per_page=1, max_pages=2)
    assert requests == [1, 2]
