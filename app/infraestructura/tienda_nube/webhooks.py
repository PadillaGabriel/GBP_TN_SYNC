from __future__ import annotations

import hashlib
import hmac


class FirmaWebhookTiendaNubeInvalidaError(PermissionError):
    """La firma HMAC del webhook no coincide con el cuerpo recibido."""


def verificar_firma_webhook(
    cuerpo: bytes,
    firma_recibida: str | None,
    secreto: str,
) -> None:
    """Valida ``x-linkedstore-hmac-sha256`` usando HMAC-SHA256 hexadecimal."""

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

    esperada = hmac.new(
        secreto_normalizado.encode("utf-8"),
        cuerpo,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(esperada, firma.lower()):
        raise FirmaWebhookTiendaNubeInvalidaError(
            "Firma de webhook Tiendanube inválida"
        )
