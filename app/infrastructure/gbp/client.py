import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GBPClient:
    """Cliente de bajo nivel para GBP.

    No normaliza datos. Solo transporta solicitudes y devuelve respuestas crudas.
    """

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.timeout = httpx.Timeout(timeout_seconds)

    async def call_soap_method(self, method_name: str, payload: str) -> str:
        """Ejecuta llamada SOAP genérica.

        El envelope definitivo depende de la documentación GBP/Módulo 16.
        """

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": method_name,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.base_url, content=payload, headers=headers)
            response.raise_for_status()
            logger.info("gbp_call_ok", extra={"method": method_name})
            return response.text

    async def call_rest_method(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta llamada REST genérica si el método validado lo requiere."""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url.rstrip('/')}/{path}", params=params)
            response.raise_for_status()
            logger.info("gbp_rest_call_ok", extra={"path": path})
            return response.json()
