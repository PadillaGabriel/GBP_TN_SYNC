from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.domain.errors import GBPProductoNoConsultableError
from app.infrastructure.gbp.xml_parser import (
    decode_gbp_response,
    extract_result_text,
    parse_dataset_tables,
)

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
        if "token expired" in lower:
            raise RuntimeError("GBP devolvió token expirado al autenticar")
        return token

    async def obtener_catalogo_basico(self, token: str) -> list[dict[str, str]]:
        """Obtiene catálogo básico completo de artículos."""

        call = await self.call_soap_method(
            "ItemBasicData_funGetXMLData",
            token=token,
            params={"bitOnlyNewOrUpdated": False},
        )
        return parse_dataset_tables(call.result_text)

    async def obtener_item_id_por_codigo(self, token: str, sku: str) -> str | None:
        """Resuelve código/SKU GBP a item_id interno."""

        sku_normalizado = str(sku or "").strip()

        if not sku_normalizado:
            return None

        call = await self.call_soap_method(
            "wsgetItemIDfromCode_funGetXMLData",
            token=token,
            params={"strItemCode": sku_normalizado},
        )

        rows = parse_dataset_tables(call.result_text)

        logger.info(
            "gbp_item_id_por_codigo_result",
            extra={
                "sku": sku_normalizado,
                "method": "wsgetItemIDfromCode_funGetXMLData",
                "rows": len(rows),
                "result_len": len(call.result_text or ""),
                "result_preview": (call.result_text or "")[:300],
            },
        )

        if not rows:
            return None

        item_id = rows[0].get("item_id")

        if not item_id:
            logger.warning(
                "gbp_item_id_por_codigo_sin_item_id",
                extra={
                    "sku": sku_normalizado,
                    "row_keys": list(rows[0].keys()),
                    "row_preview": rows[0],
                },
            )
            return None

        return item_id

    async def obtener_producto_por_id(self, token: str, item_id: int | str) -> dict[str, str]:
        """Obtiene ficha completa de un producto por item_id GBP."""

        call = await self.call_soap_method(
            "wsItem_funGetXMLDataById",
            token=token,
            params={"intItemID": int(item_id)},
        )

        rows = parse_dataset_tables(call.result_text)

        logger.info(
            "gbp_producto_por_id_result",
            extra={
                "item_id": str(item_id),
                "method": "wsItem_funGetXMLDataById",
                "rows": len(rows),
                "result_len": len(call.result_text or ""),
                "result_preview": (call.result_text or "")[:300],
            },
        )

        if not rows:
            raise GBPProductoNoConsultableError(
                f"GBP no devolvió ficha completa para item_id={item_id}"
            )

        return rows[0]

    async def obtener_precio_por_item_id(
        self,
        token: str,
        *,
        item_id: int | str,
        price_list_id: int | str,
    ) -> list[dict[str, str]]:
        """Obtiene precio del artículo en una lista de precios GBP."""

        call = await self.call_soap_method(
            "PriceListItems_funGetXMLData_Short",
            token=token,
            params={"pPriceList": price_list_id, "pItem": int(item_id)},
        )
        return parse_dataset_tables(call.result_text)

    async def obtener_stock_por_item_id(
        self,
        token: str,
        *,
        item_id: int | str,
        storage_id: int | str = -1,
    ) -> list[dict[str, str]]:
        """Obtiene stock disponible por depósito para un artículo GBP."""

        call = await self.call_soap_method(
            "ItemStorage_funGetXMLData",
            token=token,
            params={"intStor_id": storage_id, "intItem_id": int(item_id)},
        )
        return parse_dataset_tables(call.result_text)

    async def obtener_imagenes_website_por_item_id(
        self,
        token: str,
        item_id: int | str,
    ) -> dict[str, str]:
        """Obtiene URLs Website del artículo para importación completa."""

        call = await self.call_soap_method(
            "wsGetWebSiteImagesURL4WebServices",
            token=token,
            params={
                "intItemID": int(item_id),
                "bolIsAvailable4Web": True,
                "bolIsAvailable4FulljausAndProducteca": False,
            },
        )
        rows = parse_dataset_tables(call.result_text)
        return rows[0] if rows else {}

    async def call_soap_method(
        self,
        method_name: str,
        *,
        token: str = "",
        params: dict[str, object] | None = None,
    ) -> GBPCallResult:
        """Ejecuta método SOAP y devuelve el contenido del nodo *Result."""

        envelope = self._build_soap_envelope(
            token=token,
            method_name=method_name,
            params=params or {},
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{SOAP_ACTION_PREFIX}/{method_name}",
        }

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                content=envelope.encode("utf-8"),
                headers=headers,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)

        response.raise_for_status()

        soap_text = decode_gbp_response(
            content=response.content,
            fallback_text=response.text,
        )
        result_text = extract_result_text(
            soap_text=soap_text,
            method_name=method_name,
        )

        logger.info(
            "gbp_soap_call_ok",
            extra={
                "method": method_name,
                "duration_ms": duration_ms,
                "result_len": len(result_text or ""),
                "result_preview": (result_text or "")[:250],
            },
        )
        return GBPCallResult(result_text=result_text, duration_ms=duration_ms)

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
