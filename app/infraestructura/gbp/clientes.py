from __future__ import annotations

import logging
import unicodedata

from app.infraestructura.gbp.analizador_xml import parse_dataset_tables
from app.infraestructura.gbp.cliente import ClienteGBP

logger = logging.getLogger(__name__)


def normalizar_texto_gbp(valor: object) -> str:
    """Normaliza texto para GBP preservando caracteres ASCII legibles."""

    texto = " ".join(str(valor or "").strip().split())
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_tildes.encode("ascii", "ignore").decode("ascii")


def _clave_comparacion(valor: object) -> str:
    return normalizar_texto_gbp(valor).casefold()


_ALIAS_PROVINCIAS_ARGENTINA = {
    "capital federal": "ciudad autonoma de buenos aires",
    "caba": "ciudad autonoma de buenos aires",
    "ciudad de buenos aires": "ciudad autonoma de buenos aires",
    "ciudad autonoma buenos aires": "ciudad autonoma de buenos aires",
    "ciudad autonoma de buenos aires": "ciudad autonoma de buenos aires",
}


def _normalizar_provincia(country_id: int, provincia: object) -> str:
    clave = _clave_comparacion(provincia)

    if country_id == 54:
        return _ALIAS_PROVINCIAS_ARGENTINA.get(clave, clave)

    return clave


class ClienteGBPSoapAdapter:
    """Adaptador SOAP oficial para consulta y alta de clientes GBP."""

    def __init__(self, cliente: ClienteGBP) -> None:
        self._cliente = cliente

    async def buscar_por_documento(self, documento: str) -> list[dict[str, str]]:
        token = await self._cliente.autenticar()
        llamada = await self._cliente.call_soap_method(
            "CustomersByTaxNumber_funGetXMLData",
            token=token,
            params={"strTaxNumber": documento},
        )
        if "not data found" in llamada.result_text.casefold():
            return []
        return parse_dataset_tables(llamada.result_text)

    async def resolver_provincia(
        self,
        *,
        country_id: int,
        provincia: str,
    ) -> int:
        token = await self._cliente.autenticar()
        llamada = await self._cliente.call_soap_method(
            "States_funGetXMLData",
            token=token,
            params={"pCountry": country_id},
        )

        estados = parse_dataset_tables(llamada.result_text)
        buscada = _normalizar_provincia(country_id, provincia)

        coincidencias = [
            fila
            for fila in estados
            if _normalizar_provincia(
                country_id,
                fila.get("state_desc"),
            )
            == buscada
        ]

        if len(coincidencias) != 1:
            raise ValueError(
                "No se pudo resolver una provincia GBP única para "
                f"{provincia!r}. Coincidencias encontradas: "
                f"{len(coincidencias)}"
            )

        return int(str(coincidencias[0]["state_id"]).strip())

    async def crear_cliente(
        self,
        *,
        nombre: str,
        country_id: int,
        state_id: int,
        direccion: str,
        ciudad: str,
        codigo_postal: str,
        fiscal_class_id: int,
        tax_number_type_id: int,
        documento: str,
        email: str,
        telefono: str,
    ) -> int:
        token = await self._cliente.autenticar()
        llamada = await self._cliente.call_soap_method(
            "Customers_setNEWCustomer",
            token=token,
            params={
                "pname": normalizar_texto_gbp(nombre),
                "pcountry": str(country_id),
                "pstate": str(state_id),
                "paddress": normalizar_texto_gbp(direccion),
                "pcity": normalizar_texto_gbp(ciudad),
                "pzip": normalizar_texto_gbp(codigo_postal),
                "pfiscalclass": str(fiscal_class_id),
                "ptaxnumbertype": str(tax_number_type_id),
                "ptaxnumber": documento,
                "pemail": email.strip().lower(),
                "pphone": "".join(c for c in telefono if c.isdigit()),
                "pnickname": "",
                "ppass1": "",
                "ppass2": "",
            },
        )
        valor = llamada.result_text.strip()
        try:
            cust_id = int(valor)
        except ValueError as exc:
            raise RuntimeError(
                f"GBP devolvio una respuesta invalida al crear cliente: {valor}"
            ) from exc
        if cust_id <= 0:
            raise RuntimeError(f"GBP rechazo el alta de cliente con codigo {cust_id}")
        logger.info(
            "gbp_cliente_creado", extra={"cust_id": cust_id, "documento": documento}
        )
        return cust_id
