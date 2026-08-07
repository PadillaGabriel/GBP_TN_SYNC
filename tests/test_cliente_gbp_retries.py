import httpx
import pytest

from app.infraestructura.gbp.cliente import ClienteGBP


SOAP_OK = b'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <AuthenticateUserResponse xmlns="http://microsoft.com/webservices/">
      <AuthenticateUserResult>TOKEN_OK</AuthenticateUserResult>
    </AuthenticateUserResponse>
  </soap:Body>
</soap:Envelope>'''


class _FakeClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb

    async def post(self, url, content=None, headers=None):
        del content, headers
        type(self).calls += 1
        if type(self).calls == 1:
            request = httpx.Request("POST", url)
            raise httpx.ConnectTimeout("timeout transitorio", request=request)
        return httpx.Response(200, content=SOAP_OK, request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_cliente_gbp_reintenta_timeout_transitorio(monkeypatch):
    _FakeClient.calls = 0
    sleeps = []

    async def fake_sleep(value):
        sleeps.append(value)

    monkeypatch.setattr("app.infraestructura.gbp.cliente.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr("app.infraestructura.gbp.cliente.asyncio.sleep", fake_sleep)

    cliente = ClienteGBP(
        base_url="https://gbp.example/wsBasicQuery.asmx",
        username="u",
        password="p",
        timeout_seconds=1,
        retry_attempts=3,
        retry_backoff_seconds=0.25,
    )

    result = await cliente.call_soap_method("AuthenticateUser", token="", params={})

    assert result.result_text == "TOKEN_OK"
    assert _FakeClient.calls == 2
    assert sleeps == [0.25]


class _AlwaysTimeoutClient(_FakeClient):
    async def post(self, url, content=None, headers=None):
        del content, headers
        type(self).calls += 1
        raise httpx.ConnectTimeout("timeout persistente", request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_cliente_gbp_corta_al_agotar_reintentos(monkeypatch):
    _AlwaysTimeoutClient.calls = 0
    sleeps = []

    async def fake_sleep(value):
        sleeps.append(value)

    monkeypatch.setattr("app.infraestructura.gbp.cliente.httpx.AsyncClient", _AlwaysTimeoutClient)
    monkeypatch.setattr("app.infraestructura.gbp.cliente.asyncio.sleep", fake_sleep)

    cliente = ClienteGBP(
        base_url="https://gbp.example/wsBasicQuery.asmx",
        username="u",
        password="p",
        timeout_seconds=1,
        retry_attempts=3,
        retry_backoff_seconds=0.5,
    )

    with pytest.raises(httpx.ConnectTimeout):
        await cliente.call_soap_method("AuthenticateUser", token="", params={})

    assert _AlwaysTimeoutClient.calls == 3
    assert sleeps == [0.5, 1.0]
