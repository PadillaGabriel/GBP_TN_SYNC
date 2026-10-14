"""Control central de acceso al plano administrativo.

Protege las operaciones sensibles sin interferir con el webhook firmado de TN.
Railway debe recibir ADMIN_USERNAME/ADMIN_PASSWORD como variables secretas.
"""
from __future__ import annotations

import base64
import binascii
import hmac

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response

from app.configuracion import ConfiguracionAplicacion


RUTAS_ADMIN = ("/admin", "/sync", "/docs", "/redoc", "/openapi.json")


def _es_protegida(path: str) -> bool:
    if path == "/pedidos/webhooks/tienda-nube":
        return False  # La firma HMAC + identificación de tienda son el autenticador.
    if path.startswith("/pedidos/") or path == "/pedidos":
        return True
    return any(path == route or path.startswith(route + "/") for route in RUTAS_ADMIN)


def verificar_admin(request: Request, settings: ConfiguracionAplicacion) -> Response | None:
    if not _es_protegida(request.url.path):
        return None
    enforced = settings.app_env.lower() in {"production", "prod"}
    if not enforced and not (settings.admin_username or settings.admin_password):
        return None
    if not settings.admin_username or not settings.admin_password:
        return PlainTextResponse("Administración no configurada", status_code=503)
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return PlainTextResponse("Autenticación requerida", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Integrador GBP TN"'})
    try:
        raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return PlainTextResponse("Credenciales inválidas", status_code=401)
    if not (
        hmac.compare_digest(username, settings.admin_username)
        and hmac.compare_digest(password, settings.admin_password)
    ):
        return PlainTextResponse("Credenciales inválidas", status_code=401)
    return None
