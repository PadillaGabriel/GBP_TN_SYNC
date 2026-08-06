from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from time import perf_counter
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.infraestructura.gbp.analizador_xml import (
    decode_gbp_response,
    extract_result_text,
)

logger = logging.getLogger(__name__)

SOAP_NAMESPACE = "http://microsoft.com/webservices/"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"


@dataclass(frozen=True)
class ClientePedidoVentaGBP:
    base_url: str
    username: str
    password: str
    company_id: str
    web_service_id: str
    branch_id: int
    language_id: int
    timeout_seconds: int = 20

    async def probar_conexion(self) -> dict[str, object]:
        await self.autenticar()
        return {
            "ok": True,
            "codigo": "GBP_SALE_ORDER_AUTH_OK",
            "mensaje": "Autenticacion correcta",
            "token_recibido": True,
            "endpoint": self.base_url,
            "sucursal_id": self.branch_id,
            "idioma_id": self.language_id,
        }

    async def autenticar(self) -> str:
        token = (await self._llamar("AuthenticateUser", token="", params={})).strip()
        if not token or "password" in token.casefold() or "invalid" in token.casefold():
            raise RuntimeError(f"Fallo AuthenticateUser en wsSaleOrder: {token}")
        return token

    async def obtener_identificador(self, token: str) -> str:
        bruto = (
            await self._llamar("Identifier_funGetData", token=token, params={})
        ).strip()
        if not bruto or bruto.startswith("-"):
            raise RuntimeError(f"Identifier_funGetData retorno invalido: {bruto!r}")
        from app.infraestructura.gbp.analizador_xml import parse_dataset_tables

        rows = parse_dataset_tables(bruto)
        guid = str((rows[0].get("guid") if rows else bruto) or "").strip()
        if not guid:
            raise RuntimeError(
                f"Identifier_funGetData no devolvio GUID util: {bruto!r}"
            )
        return guid

    async def insertar_item(
        self,
        token: str,
        *,
        guid: str,
        deposito_id: int,
        item_id: int,
        lista_precio_id: int,
        cantidad: Decimal,
        precio: Decimal,
        moneda_id: int,
    ) -> str:
        return await self._llamar(
            "Item_funInsertData_withPrice",
            token=token,
            params={
                "pGuid": guid,
                "pStor": deposito_id,
                "pItem": item_id,
                "pPrli": lista_precio_id,
                "pQty": cantidad,
                "pPrice": precio,
                "pCurrID": moneda_id,
            },
        )

    async def mantener_vivo(self, token: str, guid: str) -> str:
        return await self._llamar(
            "SaleOrder_updateIsEditing",
            token=token,
            params={"pGuid": guid},
        )

    async def obtener_datos_por_guid(self, token: str, guid: str) -> str:
        return await self._llamar(
            "SaleOrder_fungetDataByGuid",
            token=token,
            params={"pGuid": guid},
        )

    async def confirmar_pedido(
        self,
        token: str,
        *,
        guid: str,
        cliente_id: int,
        tipo_documento_id: int,
        condicion_venta_id: int,
        transporte_id: int,
        descuento_id: int,
        observacion_1: str,
        observacion_2: str,
        observacion_3: str,
        observacion_4: str,
    ) -> str:
        return await self._llamar(
            "SaleOrder_funInsertDataV3",
            token=token,
            params={
                "pGuid": guid,
                "intCust_Id": cliente_id,
                "intSD_Id": tipo_documento_id,
                "intST_Id": condicion_venta_id,
                "intDL_Id": transporte_id,
                "intDisc_Id": descuento_id,
                "strSOH_Observation1": observacion_1,
                "strSOH_Observation2": observacion_2,
                "strSOH_Observation3": observacion_3,
                "strSOH_Observation4": observacion_4,
            },
        )

    async def obtener_totales(
        self,
        token: str,
        *,
        guid: str,
        cliente_id: int,
        tipo_documento_id: int,
    ) -> str:
        return await self._llamar(
            "SaleOrder_funGetTotals",
            token=token,
            params={
                "pGuid": guid,
                "pCust": cliente_id,
                "pDocument": tipo_documento_id,
            },
        )

    async def _llamar(
        self, method_name: str, *, token: str, params: dict[str, Any]
    ) -> str:
        cuerpo = "".join(
            f"<{nombre}>{escape(self._valor(valor))}</{nombre}>"
            for nombre, valor in params.items()
        )
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="{SOAP_ENV}">
  <soap:Header>
    <wsSaleOrderHeader xmlns="{SOAP_NAMESPACE}">
      <pUsername>{escape(self.username)}</pUsername>
      <pPassword>{escape(self.password)}</pPassword>
      <pCompany>{escape(str(self.company_id))}</pCompany>
      <pWebWervice>{escape(str(self.web_service_id))}</pWebWervice>
      <pBranch>{self.branch_id}</pBranch>
      <pLanguage>{self.language_id}</pLanguage>
      <pAuthenticatedToken>{escape(token)}</pAuthenticatedToken>
    </wsSaleOrderHeader>
  </soap:Header>
  <soap:Body>
    <{method_name} xmlns="{SOAP_NAMESPACE}">{cuerpo}</{method_name}>
  </soap:Body>
</soap:Envelope>"""
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{SOAP_NAMESPACE.rstrip("/")}/{method_name}"',
        }
        inicio = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds)
            ) as client:
                response = await client.post(
                    self.base_url, content=envelope.encode("utf-8"), headers=headers
                )
        except Exception:
            logger.exception(
                "gbp_soap_error_transporte metodo=%s endpoint=%s duracion_ms=%s",
                method_name,
                self.base_url,
                round((perf_counter() - inicio) * 1000, 2),
            )
            raise
        duracion_ms = round((perf_counter() - inicio) * 1000, 2)
        logger.info(
            "gbp_soap_respuesta metodo=%s status=%s duracion_ms=%s bytes=%s",
            method_name,
            response.status_code,
            duracion_ms,
            len(response.content),
        )
        if response.status_code >= 400:
            cuerpo_error = decode_gbp_response(
                content=response.content, fallback_text=response.text
            )
            raise RuntimeError(
                f"GBP SOAP error method={method_name} status={response.status_code} "
                f"body={cuerpo_error[:2000]}"
            )
        soap_text = decode_gbp_response(
            content=response.content, fallback_text=response.text
        )
        return extract_result_text(soap_text=soap_text, method_name=method_name)

    @staticmethod
    def _valor(valor: Any) -> str:
        if isinstance(valor, bool):
            return "true" if valor else "false"
        if isinstance(valor, Decimal):
            return format(valor, "f")
        return str(valor)
