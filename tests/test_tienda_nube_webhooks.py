import base64
import hashlib
import hmac

import pytest

from app.infraestructura.tienda_nube.webhooks import (
    FirmaWebhookTiendaNubeInvalidaError,
    verificar_firma_webhook,
)


def _firma(cuerpo: bytes, secreto: str) -> str:
    digest = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_verificar_firma_webhook_valida() -> None:
    cuerpo = b'{"store_id":123,"event":"order/paid","id":456}'
    verificar_firma_webhook(cuerpo, _firma(cuerpo, "secreto"), "secreto")


def test_verificar_firma_webhook_rechaza_firma_incorrecta() -> None:
    with pytest.raises(FirmaWebhookTiendaNubeInvalidaError):
        verificar_firma_webhook(b"{}", "incorrecta", "secreto")


def test_verificar_firma_webhook_exige_secreto() -> None:
    with pytest.raises(FirmaWebhookTiendaNubeInvalidaError):
        verificar_firma_webhook(b"{}", "firma", "")

from types import SimpleNamespace

from fastapi import BackgroundTasks
from starlette.requests import Request

from app.presentacion import rutas_pedidos


def _request(cuerpo: bytes, firma: str) -> Request:
    enviado = False

    async def receive():
        nonlocal enviado
        if enviado:
            return {"type": "http.request", "body": b"", "more_body": False}
        enviado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/pedidos/webhooks/tienda-nube",
            "headers": [(b"x-linkedstore-hmac-sha256", firma.encode())],
        },
        receive,
    )


@pytest.mark.asyncio
async def test_webhook_aceptado_encola_orquestador_automatico(monkeypatch) -> None:
    secreto = "secreto"
    cuerpo = b'{"store_id":123,"event":"order/paid","id":456}'
    configuracion = SimpleNamespace(
        tienda_nube_webhook_secret=secreto,
        tienda_nube_store_id="123",
        tienda_nube_webhook_event_list=["order/paid"],
        tienda_nube_pedidos_automaticos_habilitados=True,
    )
    monkeypatch.setattr(rutas_pedidos, "obtener_configuracion", lambda: configuracion)
    tareas = BackgroundTasks()

    resultado = await rutas_pedidos.recibir_webhook_tienda_nube(
        _request(cuerpo, _firma(cuerpo, secreto)), tareas
    )

    assert resultado == {
        "ok": True,
        "aceptado": True,
        "evento": "order/paid",
        "order_id": "456",
    }
    assert len(tareas.tasks) == 1
    tarea = tareas.tasks[0]
    assert tarea.func is rutas_pedidos._procesar_pedido_tienda_nube_en_segundo_plano
    assert tarea.args == ("456",)


@pytest.mark.asyncio
async def test_tarea_segundo_plano_construye_y_ejecuta_orquestador(monkeypatch) -> None:
    llamadas: list[str] = []

    class SesionFalsa:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class ProcesadorFalso:
        async def ejecutar(self, order_id: str):
            llamadas.append(order_id)
            return {"ok": True}

    monkeypatch.setattr(rutas_pedidos, "SessionLocal", lambda: SesionFalsa())
    monkeypatch.setattr(
        rutas_pedidos,
        "construir_procesador_pedido_tienda_nube",
        lambda sesion: ProcesadorFalso(),
    )

    await rutas_pedidos._procesar_pedido_tienda_nube_en_segundo_plano("456")

    assert llamadas == ["456"]
