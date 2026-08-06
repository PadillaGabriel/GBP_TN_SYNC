from __future__ import annotations

import base64
import hashlib
import hmac


class FirmaWebhookTiendaNubeInvalidaError(PermissionError):
    """La firma HMAC del webhook no coincide con el cuerpo recibido."""


def verificar_firma_webhook(
    cuerpo: bytes,
    firma_recibida: str | None,
    secreto: str,
) -> None:
    """Valida ``x-linkedstore-hmac-sha256`` usando HMAC-SHA256 en base64."""

    firma = str(firma_recibida or "").strip()
    secreto_normalizado = str(secreto or "").strip()
    if not secreto_normalizado:
        raise FirmaWebhookTiendaNubeInvalidaError(
            "TIENDA_NUBE_WEBHOOK_SECRET no está configurado"
        )
    if not firma:
        raise FirmaWebhookTiendaNubeInvalidaError(
            "Falta el encabezado x-linkedstore-hmac-sha256"
        )

    digest = hmac.new(
        secreto_normalizado.encode("utf-8"),
        cuerpo,
        hashlib.sha256,
    ).digest()
    esperada = base64.b64encode(digest).decode("ascii")
    if not hmac.compare_digest(esperada, firma):
        raise FirmaWebhookTiendaNubeInvalidaError(
            "Firma de webhook Tiendanube inválida"
        )
