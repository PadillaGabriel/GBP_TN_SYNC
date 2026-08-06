from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

from app.aplicacion.puertos.cliente_gbp import ClienteGBPPuerto
from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto
from app.configuracion import ConfiguracionAplicacion


class PedidoNoEncontradoParaAltaClienteError(LookupError):
    pass


class DatosClienteGBPInvalidosError(ValueError):
    pass


class EscrituraClienteGBPDeshabilitadaError(PermissionError):
    pass


class AltaClienteGBPError(RuntimeError):
    pass


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    normalizado = " ".join(str(valor).strip().split())
    return normalizado or None


def _texto_sin_tildes(valor: object) -> str | None:
    texto = _texto(valor)
    if texto is None:
        return None
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _documento_normalizado(valor: object) -> str | None:
    texto = _texto(valor)
    if texto is None:
        return None
    digitos = re.sub(r"\D", "", texto)
    return digitos or None


def _tipo_documento_id(documento: str, tipo: object) -> int:
    descripcion = (_texto_sin_tildes(tipo) or "").upper()
    if "CUIT" in descripcion or len(documento) == 11:
        return 1
    return 5


class CrearClienteGBP:
    """Resuelve o crea un cliente mediante Customers_setNEWCustomer."""

    def __init__(
        self,
        repositorio: RepositorioPedidosPuerto,
        cliente_gbp: ClienteGBPPuerto,
        configuracion: ConfiguracionAplicacion,
    ) -> None:
        self._repositorio = repositorio
        self._cliente_gbp = cliente_gbp
        self._configuracion = configuracion

    async def ejecutar(self, pedido_id: int) -> dict[str, object]:
        pedido = self._repositorio.obtener_por_id_para_validacion(pedido_id)
        if pedido is None:
            raise PedidoNoEncontradoParaAltaClienteError(
                f"Pedido {pedido_id} no encontrado"
            )

        cliente = pedido.get("cliente") or {}
        envio = pedido.get("envio") or {}
        nombre = _texto(
            " ".join(
                parte
                for parte in (
                    str(cliente.get("nombre") or "").strip(),
                    str(cliente.get("apellido") or "").strip(),
                )
                if parte
            )
        )
        documento = _documento_normalizado(cliente.get("numero_documento"))
        email = _texto(cliente.get("email"))
        provincia = _texto(envio.get("provincia"))
        direccion = _texto(envio.get("direccion"))
        ciudad = _texto(envio.get("ciudad"))
        codigo_postal = _texto(envio.get("codigo_postal"))
        telefono = _texto(cliente.get("telefono")) or ""

        errores: list[str] = []
        if not nombre:
            errores.append("CLIENTE_NOMBRE_REQUERIDO")
        if not documento:
            errores.append("CLIENTE_DOCUMENTO_REQUERIDO")
        elif len(documento) not in {7, 8, 11}:
            errores.append("CLIENTE_DOCUMENTO_FORMATO_INVALIDO")
        if not email:
            errores.append("CLIENTE_EMAIL_REQUERIDO")
        if not provincia:
            errores.append("CLIENTE_PROVINCIA_REQUERIDA")
        if not direccion:
            errores.append("CLIENTE_DIRECCION_REQUERIDA")
        if not ciudad:
            errores.append("CLIENTE_CIUDAD_REQUERIDA")
        if not codigo_postal:
            errores.append("CLIENTE_CODIGO_POSTAL_REQUERIDO")
        if errores:
            raise DatosClienteGBPInvalidosError("; ".join(errores))

        cfg = self._configuracion
        request_id = str(uuid4())
        correlation_id = str(pedido.get("correlation_id") or request_id)
        tipo_documento_id = _tipo_documento_id(documento, cliente.get("tipo_documento"))
        country_id = cfg.pedidos_gbp_customer_country_id
        fiscal_class_id = cfg.pedidos_gbp_customer_fiscal_class_id

        plan = {
            "method": "Customers_setNEWCustomer",
            "country_id": country_id,
            "province": provincia,
            "fiscal_class_id": fiscal_class_id,
            "tax_number_type_id": tipo_documento_id,
            "customer": {
                "name": _texto_sin_tildes(nombre),
                "tax_number": documento,
                "email": email.lower(),
                "phone": telefono,
                "address": _texto_sin_tildes(direccion),
                "city": _texto_sin_tildes(ciudad),
                "postal_code": codigo_postal,
            },
        }

        existentes = await self._cliente_gbp.buscar_por_documento(documento)
        if len(existentes) > 1:
            raise AltaClienteGBPError("CLIENTE_GBP_AMBIGUO")
        if len(existentes) == 1:
            cust_id = int(str(existentes[0]["cust_id"]).strip())
            self._repositorio.vincular_cliente_gbp(pedido_id, cust_id)
            return {
                "ok": True,
                "pedido_id": pedido_id,
                "codigo": "CLIENTE_GBP_YA_EXISTE",
                "modo": "IDEMPOTENTE",
                "escritura_ejecutada": False,
                "cust_id": cust_id,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "plan": plan,
            }

        if cfg.dry_run:
            state_id = await self._cliente_gbp.resolver_provincia(
                country_id=country_id,
                provincia=provincia,
            )
            plan["state_id"] = state_id
            return {
                "ok": True,
                "pedido_id": pedido_id,
                "codigo": "CLIENTE_GBP_ALTA_SIMULADA",
                "modo": "SIMULACION",
                "escritura_ejecutada": False,
                "requiere_confirmacion": True,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "flags": {
                    "dry_run": cfg.dry_run,
                    "pedidos_escritura_gbp_habilitada": cfg.pedidos_escritura_gbp_habilitada,
                },
                "plan": plan,
            }

        if not cfg.pedidos_escritura_gbp_habilitada:
            raise EscrituraClienteGBPDeshabilitadaError("GBP_CUSTOMER_WRITE_DISABLED")

        state_id = await self._cliente_gbp.resolver_provincia(
            country_id=country_id,
            provincia=provincia,
        )
        try:
            cust_id_retornado = await self._cliente_gbp.crear_cliente(
                nombre=nombre,
                country_id=country_id,
                state_id=state_id,
                direccion=direccion,
                ciudad=ciudad,
                codigo_postal=codigo_postal,
                fiscal_class_id=fiscal_class_id,
                tax_number_type_id=tipo_documento_id,
                documento=documento,
                email=email,
                telefono=telefono,
            )
        except (RuntimeError, ValueError) as exc:
            raise AltaClienteGBPError(f"CLIENTE_GBP_ALTA_RECHAZADA: {exc}") from exc
        posteriores = await self._cliente_gbp.buscar_por_documento(documento)
        if len(posteriores) != 1:
            raise AltaClienteGBPError(
                "CLIENTE_GBP_ALTA_NO_VERIFICADA: la consulta posterior no devolvio una coincidencia unica"
            )
        cust_id_verificado = int(str(posteriores[0]["cust_id"]).strip())
        if cust_id_verificado != cust_id_retornado:
            raise AltaClienteGBPError(
                f"CLIENTE_GBP_ID_INCONSISTENTE: retorno={cust_id_retornado}, verificado={cust_id_verificado}"
            )

        self._repositorio.vincular_cliente_gbp(pedido_id, cust_id_verificado)
        return {
            "ok": True,
            "pedido_id": pedido_id,
            "codigo": "CLIENTE_GBP_CREADO",
            "modo": "ESCRITURA_CONTROLADA",
            "escritura_ejecutada": True,
            "cust_id": cust_id_verificado,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "sent_at_utc": datetime.now(UTC).isoformat(),
            "plan": {**plan, "state_id": state_id},
        }
