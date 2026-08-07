from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.dominio.errores import GBPProductoNoConsultableError
from app.infraestructura.gbp.analizador_xml import (
    decode_gbp_response,
    extract_result_text,
    parse_dataset_tables,
)

logger = logging.getLogger(__name__)


def normalizar_sku_para_gbp(sku: str | None) -> str:
    """
    Normalizacion conservadora para consultar GBP.

    No elimina letras, numeros ni separadores internos. Solo limpia espacios
    externos y caracteres invisibles frecuentes.
    """
    return (
        str(sku or "")
        .replace("\u00a0", " ")
        .replace("\t", " ")
        .replace("\r", "")
        .replace("\n", "")
        .strip()
    )


def _get_first_value(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    """Obtiene el primer valor no vacio tolerando variantes de nombre de columna GBP."""
    if not row:
        return None

    for candidate in candidates:
        value = row.get(candidate)
        if value not in (None, ""):
            return str(value).strip()

    lower_map = {str(key).lower(): value for key, value in row.items()}
    for candidate in candidates:
        value = lower_map.get(candidate.lower())
        if value not in (None, ""):
            return str(value).strip()

    normalized_map = {
        "".join(ch for ch in str(key).lower() if ch.isalnum()): value
        for key, value in row.items()
    }
    for candidate in candidates:
        normalized = "".join(ch for ch in candidate.lower() if ch.isalnum())
        value = normalized_map.get(normalized)
        if value not in (None, ""):
            return str(value).strip()

    return None


SOAP_NAMESPACE = "http://microsoft.com/webservices/"
SOAP_ACTION_PREFIX = SOAP_NAMESPACE.rstrip("/")
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"


@dataclass(frozen=True)
class GBPCallResult:
    """Resultado interno de una llamada GBP."""

    result_text: str
    duration_ms: int


class ClienteGBP:
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
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.company_id = company_id
        self.web_service_id = web_service_id
        self.timeout = httpx.Timeout(timeout_seconds)
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

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

        sku_normalizado = normalizar_sku_para_gbp(sku)

        if not sku_normalizado:
            logger.warning(
                "gbp_item_id_por_codigo_sku_vacio", extra={"sku_original": sku}
            )
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
                "sku_original": sku,
                "sku_normalizado": sku_normalizado,
                "method": "wsgetItemIDfromCode_funGetXMLData",
                "rows": len(rows),
                "result_len": len(call.result_text or ""),
                "result_preview": (call.result_text or "")[:500],
                "row_keys": list(rows[0].keys()) if rows else [],
                "row_preview": rows[0] if rows else None,
            },
        )

        if not rows:
            return None

        item_id = _get_first_value(
            rows[0],
            (
                "item_id",
                "Item_ID",
                "ItemID",
                "itemID",
                "intItemID",
                "intItem_id",
                "id",
            ),
        )

        if not item_id:
            logger.warning(
                "gbp_item_id_por_codigo_sin_item_id",
                extra={
                    "sku_original": sku,
                    "sku_normalizado": sku_normalizado,
                    "row_keys": list(rows[0].keys()),
                    "row_preview": rows[0],
                },
            )
            return None

        logger.info(
            "gbp_item_id_por_codigo_ok",
            extra={
                "sku_original": sku,
                "sku_normalizado": sku_normalizado,
                "item_id": item_id,
            },
        )
        return item_id

    async def obtener_producto_por_id(
        self, token: str, item_id: int | str
    ) -> dict[str, str]:
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

    async def obtener_producto_basico_por_id(
        self,
        token: str,
        item_id: int | str,
    ) -> dict[str, str] | None:
        """
        Fallback para obtener datos mínimos del producto desde ItemBasicData_funGetXMLData.

        Se usa cuando wsItem_funGetXMLDataById no devuelve ficha completa,
        pero el producto sí existe en el catálogo básico.
        """

        catalogo = await self.obtener_catalogo_basico(token)
        item_id_str = str(item_id).strip()

        for row in catalogo:
            row_item_id = _get_first_value(
                row,
                (
                    "item_id",
                    "Item_ID",
                    "ItemID",
                    "itemID",
                    "intItemID",
                    "intItem_id",
                    "id",
                ),
            )

            if str(row_item_id or "").strip() != item_id_str:
                continue

            item_code = _get_first_value(
                row,
                (
                    "item_code",
                    "ItemCode",
                    "itemCode",
                    "code",
                    "Code",
                    "codigo",
                    "Codigo",
                    "item_barcode",
                    "item_vendorCode",
                ),
            )
            item_desc = _get_first_value(
                row,
                (
                    "item_desc",
                    "ItemDesc",
                    "itemDesc",
                    "description",
                    "Description",
                    "descripcion",
                    "Descripcion",
                    "name",
                    "Name",
                ),
            )

            detalle_basico = {
                **row,
                "item_id": item_id_str,
                "item_code": str(item_code or "").strip(),
                "item_desc": str(
                    item_desc or item_code or f"Producto {item_id_str}"
                ).strip(),
                "item_web": row.get("item_web", ""),
                "item_disabled": row.get("item_disabled", "false"),
                "item_not4Sale": row.get("item_not4Sale", "false"),
            }

            logger.info(
                "gbp_producto_basico_por_id_ok",
                extra={
                    "item_id": item_id_str,
                    "method": "ItemBasicData_funGetXMLData",
                    "row_keys": list(row.keys()),
                    "sku": detalle_basico.get("item_code"),
                    "titulo": detalle_basico.get("item_desc"),
                },
            )
            return detalle_basico

        logger.warning(
            "gbp_producto_basico_por_id_no_match",
            extra={
                "item_id": item_id_str,
                "method": "ItemBasicData_funGetXMLData",
                "catalogo_rows": len(catalogo),
            },
        )
        return None

    async def obtener_producto_por_id_robusto(
        self,
        token: str,
        item_id: int | str,
    ) -> dict[str, str]:
        """
        Obtiene producto por item_id usando método principal y fallback.

        1. wsItem_funGetXMLDataById
        2. ItemBasicData_funGetXMLData
        """

        try:
            return await self.obtener_producto_por_id(token, item_id)
        except GBPProductoNoConsultableError:
            logger.warning(
                "gbp_producto_por_id_fallback_catalogo_basico",
                extra={
                    "item_id": str(item_id),
                    "fallback_method": "ItemBasicData_funGetXMLData",
                },
            )

        fallback = await self.obtener_producto_basico_por_id(token, item_id)

        if fallback:
            return fallback

        raise GBPProductoNoConsultableError(
            f"GBP no devolvió ficha completa ni ficha básica para item_id={item_id}"
        )

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

    async def obtener_exportacion(self, export_id: int) -> list[dict[str, str]]:
        """Ejecuta una Exportación Personalizada y renueva el token si vence."""

        token = await self.autenticar()
        call = await self.call_soap_method(
            "wsExportDataById",
            token=token,
            params={"intExpgr_id": int(export_id)},
        )
        if "token expired" in (call.result_text or "").lower():
            token = await self.autenticar()
            call = await self.call_soap_method(
                "wsExportDataById",
                token=token,
                params={"intExpgr_id": int(export_id)},
            )
        text = (call.result_text or "").strip()
        if not text:
            return []
        if "token expired" in text.lower():
            raise RuntimeError("GBP no aceptó el token al ejecutar wsExportDataById")
        return parse_dataset_tables(text)

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

        response: httpx.Response | None = None
        start = time.perf_counter()
        retryable_exceptions = (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )

        for attempt in range(1, self.retry_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.base_url,
                        content=envelope.encode("utf-8"),
                        headers=headers,
                    )
                if response.status_code in (429, 502, 503, 504) and attempt < self.retry_attempts:
                    delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "gbp_soap_retry_http",
                        extra={
                            "method": method_name,
                            "attempt": attempt,
                            "max_attempts": self.retry_attempts,
                            "status_code": response.status_code,
                            "delay_seconds": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                break
            except retryable_exceptions as exc:
                if attempt >= self.retry_attempts:
                    logger.error(
                        "gbp_soap_retry_exhausted",
                        extra={
                            "method": method_name,
                            "attempts": attempt,
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise
                delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "gbp_soap_retry_transport",
                    extra={
                        "method": method_name,
                        "attempt": attempt,
                        "max_attempts": self.retry_attempts,
                        "error_type": type(exc).__name__,
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)

        if response is None:
            raise RuntimeError(f"GBP no devolvió respuesta para {method_name}")

        duration_ms = int((time.perf_counter() - start) * 1000)

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
            response = await client.get(
                f"{self.base_url.rstrip('/')}/{path}", params=params
            )
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
            f"<{name}>{self._safe_xml_value(value)}</{name}>"
            for name, value in params.items()
        )
        return f"""<?xml version="1.0" encoding="utf-8"?>
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
</soap:Envelope>"""

    @staticmethod
    def _safe_xml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return escape(str(value))
