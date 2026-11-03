import httpx
import pytest

from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube


def client():
    return ClienteTiendaNube(base_url="https://example.test", store_id="123", access_token="t", timeout_seconds=3)


@pytest.mark.asyncio
async def test_exact_full_page_ends_by_total_count_without_requesting_404(monkeypatch):
    seen = []

    async def fake(self, session, method, url, **kwargs):
        page = kwargs["params"]["page"]
        seen.append(page)
        assert page == 1, "No debe pedir la segunda página cuando el total ya está completo"
        return httpx.Response(200, request=httpx.Request("GET", url),
                              headers={"x-total-count": "2"},
                              json=[{"id": 1}, {"id": 2}])

    monkeypatch.setattr(ClienteTiendaNube, "_request_with_retries", fake)
    assert len(await client().list_categories(per_page=2)) == 2
    assert seen == [1]


@pytest.mark.asyncio
async def test_link_without_next_stops_even_when_full(monkeypatch):
    pages = []

    async def fake(self, session, method, url, **kwargs):
        pages.append(kwargs["params"]["page"])
        return httpx.Response(200, request=httpx.Request("GET", url),
                              headers={"Link": '<https://example.test/categories?page=1>; rel="last"'},
                              json=[{"id": 1}, {"id": 2}])

    monkeypatch.setattr(ClienteTiendaNube, "_request_with_retries", fake)
    assert len(await client().list_categories(per_page=2)) == 2
    assert pages == [1]


@pytest.mark.asyncio
async def test_404_without_pagination_metadata_remains_error(monkeypatch):
    async def fake(self, session, method, url, **kwargs):
        page = kwargs["params"]["page"]
        return httpx.Response(200 if page == 1 else 404,
                              request=httpx.Request("GET", url),
                              json=[{"id": 1}, {"id": 2}] if page == 1 else {})

    monkeypatch.setattr(ClienteTiendaNube, "_request_with_retries", fake)
    with pytest.raises(RuntimeError, match="sin confirmación previa"):
        await client().list_categories(per_page=2)


@pytest.mark.asyncio
async def test_inconsistent_total_blocks_partial_catalog(monkeypatch):
    async def fake(self, session, method, url, **kwargs):
        return httpx.Response(200, request=httpx.Request("GET", url),
                              headers={"x-total-count": "3"}, json=[{"id": 1}])

    monkeypatch.setattr(ClienteTiendaNube, "_request_with_retries", fake)
    with pytest.raises(RuntimeError, match="faltan filas"):
        await client().list_categories(per_page=2)
