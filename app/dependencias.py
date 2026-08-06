"""Raíz de composición de dependencias de la aplicación.

Las conexiones de base de datos conservan alcance por solicitud. Los clientes y
adaptadores externos, que son inmutables y no mantienen estado transaccional,
se reutilizan para reducir construcción repetida y centralizar configuración.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.aplicacion.pedidos.casos_uso import (
    ConfirmarPedidoGBP,
    CrearClienteGBP,
    ImportarPedidoTiendaNube,
    PrepararPedidoVentaGBP,
    ProcesarPedidoTiendaNube,
)
from app.configuracion import obtener_configuracion
from app.infraestructura.gbp.adaptador import AdaptadorGBP
from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.registro_modulo16 import RegistroModulo16
from app.infraestructura.gbp.clientes import ClienteGBPSoapAdapter
from app.infraestructura.gbp.pedidos_venta import ClientePedidoVentaGBP
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios.pedidos import RepositorioPedidos
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube


def obtener_sesion_bd() -> Generator[Session, None, None]:
    """Crea una sesión de base de datos por solicitud y garantiza su cierre."""

    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


@lru_cache
def obtener_cliente_gbp() -> ClienteGBP:
    """Construye una única instancia inmutable del cliente SOAP GBP."""

    configuracion = obtener_configuracion()
    return ClienteGBP(
        base_url=configuracion.gbp_base_url,
        username=configuracion.gbp_username,
        password=configuracion.gbp_password,
        timeout_seconds=configuracion.gbp_timeout_seconds,
        company_id=configuracion.gbp_company_id,
        web_service_id=configuracion.gbp_web_service_id,
    )


@lru_cache
def obtener_adaptador_gbp() -> AdaptadorGBP:
    """Devuelve el adaptador de consultas GBP validado por el registro del módulo 16."""

    configuracion = obtener_configuracion()
    return AdaptadorGBP(
        client=obtener_cliente_gbp(),
        registry=RegistroModulo16(strict=configuracion.gbp_module16_strict),
    )


@lru_cache
def obtener_cliente_tienda_nube() -> ClienteTiendaNube:
    """Construye una única instancia inmutable del cliente Tienda Nube."""

    configuracion = obtener_configuracion()
    return ClienteTiendaNube(
        base_url=configuracion.tienda_nube_base_url,
        store_id=configuracion.tienda_nube_store_id,
        access_token=configuracion.tienda_nube_access_token,
        timeout_seconds=configuracion.tienda_nube_timeout_seconds,
    )


@lru_cache
def obtener_adaptador_tienda_nube() -> AdaptadorTiendaNube:
    """Devuelve el adaptador reutilizable de Tienda Nube."""

    return AdaptadorTiendaNube(client=obtener_cliente_tienda_nube())


@lru_cache
def obtener_cliente_gbp_pedidos() -> ClienteGBPSoapAdapter:
    """Adaptador oficial de clientes GBP para pedidos."""

    return ClienteGBPSoapAdapter(obtener_cliente_gbp())


@lru_cache
def obtener_cliente_pedido_venta_gbp() -> ClientePedidoVentaGBP:
    configuracion = obtener_configuracion()
    return ClientePedidoVentaGBP(
        base_url=configuracion.pedidos_gbp_sale_order_base_url,
        username=configuracion.gbp_username,
        password=configuracion.gbp_password,
        company_id=configuracion.gbp_company_id,
        web_service_id=configuracion.gbp_web_service_id,
        branch_id=configuracion.pedidos_gbp_branch_id,
        language_id=configuracion.pedidos_gbp_language_id,
        timeout_seconds=configuracion.gbp_timeout_seconds,
    )


def construir_procesador_pedido_tienda_nube(
    sesion: Session,
) -> ProcesarPedidoTiendaNube:
    """Compone el flujo productivo completo para una orden de Tiendanube."""

    configuracion = obtener_configuracion()
    repositorio = RepositorioPedidos(sesion)
    importador = ImportarPedidoTiendaNube(obtener_cliente_tienda_nube(), repositorio)
    creador_cliente = CrearClienteGBP(
        repositorio,
        obtener_cliente_gbp_pedidos(),
        configuracion,
    )
    preparador = PrepararPedidoVentaGBP(
        repositorio,
        obtener_cliente_gbp(),
        configuracion,
    )
    confirmador = ConfirmarPedidoGBP(
        preparador,
        obtener_cliente_pedido_venta_gbp(),
        repositorio,
        configuracion,
    )
    return ProcesarPedidoTiendaNube(importador, creador_cliente, confirmador)
