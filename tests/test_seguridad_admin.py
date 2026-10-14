"""Autenticación segura del plano administrativo."""
import base64
from types import SimpleNamespace

from starlette.requests import Request

from app.seguridad.administracion import verificar_admin


def _request(path, basic=None):
    headers = []
    if basic:
        headers.append((b"authorization", basic.encode()))
    return Request({"type": "http", "method": "GET", "path": path, "headers": headers, "query_string": b""})


def test_en_produccion_no_expone_administracion_sin_configurar():
    config = SimpleNamespace(app_env="prod", admin_username="", admin_password="")
    assert verificar_admin(_request("/admin/panel"), config).status_code == 503
    assert verificar_admin(_request("/sync/jobs/8"), config).status_code == 503
    assert verificar_admin(_request("/health"), config) is None
    assert verificar_admin(_request("/pedidos/webhooks/tienda-nube"), config) is None


def test_basic_admin_compara_secreto_correcto():
    config = SimpleNamespace(app_env="prod", admin_username="operator", admin_password="password_123")
    assert verificar_admin(_request("/admin"), config).status_code == 401
    bad = 'Basic ' + base64.b64encode(b"operator:wrong").decode()
    good = 'Basic ' + base64.b64encode(b"operator:password_123").decode()
    assert verificar_admin(_request("/admin", bad), config).status_code == 401
    assert verificar_admin(_request("/admin", good), config) is None
