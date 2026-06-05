from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.infrastructure.gbp.xml_parser import extract_result_text, parse_dataset_tables

logger = logging.getLogger(__name__)

SOAP_NAMESPACE = "http://microsoft.com/webservices/"
SOAP_ACTION_PREFIX = SOAP_NAMESPACE.rstrip("/")
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"


@dataclass(frozen=True)
class GBPCallResult:
    """Resultado interno de una llamada GBP."""

    result_text: str
    duration_ms: int


class GBPClient:
    """Cliente SOAP para métodos de lectura GBP Módulo 16."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: int,
        company_id: str = "",
        web_service_id: str = "",
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.company_id = company_id
        self.web_service_id = web_service_id
        self.timeout = httpx.Timeout(timeout_seconds)

    async def autenticar(self) -> str:
        """Autentica contra GBP y devuelve token temporal."""

        call = await self.call_soap_method("AuthenticateUser", token="", params={})
        token = call.result_text.strip()
        lower = token.lower()
        if not token or "invalid username" in lower or "password" in lower:
            raise RuntimeError(f"Falló AuthenticateUser: {token}")
        return token

    async def obtener_catalogo_basico(self, token: str) -> list[dict[str, str]]:
        """Obtiene catálogo básico completo de artículos."""

        call = await self.call_soap_method(
            "ItemBasicData_funGetXMLData",
            token=token,
            params={"bitOnlyNewOrUpdated": False},
        )
        return parse_dataset_tables(call.result_text)

    async def obtener_producto_por_id(self, token: str, item_id: int | str) -> dict[str, str]:
        """Obtiene ficha completa de un producto por item_id GBP."""

        call = await self.call_soap_method(
            "wsItem_funGetXMLDataById",
            token=token,
            params={"intItemID": int(item_id)},
        )
        rows = parse_dataset_tables(call.result_text)
        if not rows:
            raise RuntimeError(f"GBP no devolvió datos para item_id={item_id}")
        return rows[0]

    async def call_soap_method(
        self,
        method_name: str,
        payload: str | None = None,
        *,
        token: str = "",
        params: dict[str, Any] | None = None,
    ) -> GBPCallResult:
        """Ejecuta llamada SOAP.

        Se mantiene el argumento payload para compatibilidad con código existente,
        pero los métodos productivos usan params para armar el envelope.
        """

        started = time.perf_counter()
        envelope = payload or self._build_soap_envelope(
            token=token,
            method_name=method_name,
            params=params or {},
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{SOAP_ACTION_PREFIX}/{method_name}"',
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                content=envelope.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info("gbp_call_ok", extra={"method": method_name, "duration_ms": duration_ms})
        return GBPCallResult(
            result_text=extract_result_text(response.text, method_name),
            duration_ms=duration_ms,
        )

    async def call_rest_method(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta llamada REST si un método validado lo requiere."""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url.rstrip('/')}/{path}", params=params)
            response.raise_for_status()
            logger.info("gbp_rest_call_ok", extra={"path": path})
            return response.json()

    def _build_soap_envelope(
        self,
        *,
        token: str,
        method_name: str,
        params: dict[str, Any],
    ) -> str:
        body_params = "".join(
            f"<{name}>{self._safe_xml_value(value)}</{name}>" for name, value in params.items()
        )
        return f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="{SOAP_ENV}">
  <soap:Header>
    <wsBasicQueryHeader xmlns="{SOAP_NAMESPACE}">
      <pUsername>{self._safe_xml_value(self.username)}</pUsername>
      <pPassword>{self._safe_xml_value(self.password)}</pPassword>
      <pCompany>{self._safe_xml_value(self.company_id)}</pCompany>
      <pWebWervice>{self._safe_xml_value(self.web_service_id)}</pWebWervice>
      <pAuthenticatedToken>{self._safe_xml_value(token)}</pAuthenticatedToken>
    </wsBasicQueryHeader>
  </soap:Header>
  <soap:Body>
    <{method_name} xmlns="{SOAP_NAMESPACE}">{body_params}</{method_name}>
  </soap:Body>
</soap:Envelope>'''

    @staticmethod
    def _safe_xml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return escape(str(value))
