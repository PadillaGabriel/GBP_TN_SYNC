from __future__ import annotations

import hashlib
import hmac


class FirmaWebhookTiendaNubeInvalidaError(PermissionError):
    """La firma HMAC del webhook no coincide con el cuerpo recibido."""


def verificar_firma_webhook(
    cuerpo: bytes,
    firma_recibida: str | None,
    secreto: str,
    secretos_adicionales: tuple[str, ...] = (),
) -> None:
    """Valida ``x-linkedstore-hmac-sha256`` usando HMAC-SHA256 hexadecimal."""

    firma = str(firma_recibida or "").strip()
    secreto_normalizado = str(secreto or "").strip()
    secretos = tuple(secret for secret in (secreto_normalizado, *secretos_adicionales) if str(secret).strip())
    if not secretos:
        raise FirmaWebhookTiendaNubeInvalidaError(
            "TIENDA_NUBE_WEBHOOK_SECRET no está configurado"
        )
    if not firma:
        raise FirmaWebhookTiendaNubeInvalidaError(
            "Falta el encabezado x-linkedstore-hmac-sha256"
        )

    coincide = any(
        hmac.compare_digest(
            hmac.new(secret.strip().encode("utf-8"), cuerpo, hashlib.sha256).hexdigest(),
            firma.lower(),
        )
        for secret in secretos
    )
    if not coincide:
        raise FirmaWebhookTiendaNubeInvalidaError(
            "Firma de webhook Tiendanube inválida"
        )
