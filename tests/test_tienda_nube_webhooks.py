"""El webhook responde éxito únicamente después de registrar el job."""
import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from app.presentacion import rutas_pedidos


def _firma(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _request(body: bytes, signature: str) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "POST", "path": "/pedidos/webhooks/tienda-nube",
         "headers": [(b"x-linkedstore-hmac-sha256", signature.encode())]},
        receive,
    )


@pytest.mark.asyncio
async def test_webhook_aceptado_persiste_job_y_retorna_id(monkeypatch) -> None:
    secret = "secreto"
    body = b'{"store_id":123,"event":"order/paid","id":456}'
    config = SimpleNamespace(
        tienda_nube_webhook_secret=secret,
        tienda_nube_store_id="123",
        tienda_nube_webhook_event_list=["order/paid"],
        tienda_nube_pedidos_automaticos_habilitados=True,
    )
    monkeypatch.setattr(rutas_pedidos, "obtener_configuracion", lambda: config)
    seen = []

    class FakeRepo:
        def __init__(self, db):
            pass

        def crear(self, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(id=42)

    monkeypatch.setattr(rutas_pedidos, "RepositorioTrabajosSincronizacion", FakeRepo)
    result = await rutas_pedidos.recibir_webhook_tienda_nube(
        _request(body, _firma(body, secret)), Mock()
    )
    assert result == {"ok": True, "aceptado": True, "evento": "order/paid", "order_id": "456", "job_id": 42}
    assert seen[0]["idempotency_key"] == "tn:123:order/paid:456"
    assert seen[0]["payload"] == {"order_id": "456"}


@pytest.mark.asyncio
async def test_webhook_no_acepta_si_falla_persistencia(monkeypatch) -> None:
    secret = "secreto"
    body = b'{"store_id":123,"event":"order/paid","id":456}'
    monkeypatch.setattr(
        rutas_pedidos, "obtener_configuracion", lambda: SimpleNamespace(
            tienda_nube_webhook_secret=secret,
            tienda_nube_store_id="123",
            tienda_nube_webhook_event_list=["order/paid"],
            tienda_nube_pedidos_automaticos_habilitados=True,
        )
    )

    class BrokenRepo:
        def __init__(self, db):
            pass

        def crear(self, **kwargs):
            raise RuntimeError("DB down")

    monkeypatch.setattr(rutas_pedidos, "RepositorioTrabajosSincronizacion", BrokenRepo)
    with pytest.raises(RuntimeError, match="DB down"):
        await rutas_pedidos.recibir_webhook_tienda_nube(
            _request(body, _firma(body, secret)), Mock()
        )
