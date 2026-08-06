from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.aplicacion.pedidos.casos_uso import (
    ConsultarPedido,
    ImportarPedidoTiendaNube,
    PedidoTiendaNubeInvalidoError,
    PedidoTiendaNubeNoEncontradoError,
    RecibirPedido,
    PrepararClienteGBP,
    PedidoNoEncontradoParaClienteError,
    CrearClienteGBP,
    AltaClienteGBPError,
    DatosClienteGBPInvalidosError,
    EscrituraClienteGBPDeshabilitadaError,
    PedidoNoEncontradoParaAltaClienteError,
    PrepararPedidoVentaGBP,
    PedidoNoEncontradoParaPreparacionGBPError,
    ClienteGBPNoVinculadoError,
    ArticuloGBPNoResueltoError,
    TotalesPedidoInconsistentesError,
    CargarPedidoTemporalGBP,
    CargaTemporalGBPDeshabilitadaError,
    InsercionItemTemporalGBPError,
    ConfirmarPedidoGBP,
    ConfirmacionPedidoGBPDeshabilitadaError,
    PedidoGBPNoConciliadoError,
    ConfirmacionPedidoGBPError,
    ConfirmacionPedidoGBPEnCursoError,
)
from app.configuracion import obtener_configuracion
from app.dependencias import (
    construir_procesador_pedido_tienda_nube,
    obtener_cliente_tienda_nube,
    obtener_cliente_gbp_pedidos,
    obtener_cliente_gbp,
    obtener_cliente_pedido_venta_gbp,
    obtener_sesion_bd,
)
from app.dominio.pedidos import (
    ClientePedidoExterno,
    DireccionEnvioPedido,
    ItemPedidoExterno,
    PedidoExterno,
)
from app.infraestructura.persistencia.base_datos import SessionLocal
from app.infraestructura.persistencia.repositorios.pedidos import RepositorioPedidos
from app.infraestructura.tienda_nube.webhooks import (
    FirmaWebhookTiendaNubeInvalidaError,
    verificar_firma_webhook,
)

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


class ClienteEntrada(BaseModel):
    external_customer_id: str | None = None
    nombre: str = Field(min_length=1, max_length=150)
    apellido: str = Field(min_length=1, max_length=150)
    email: str | None = None
    telefono: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None


class EnvioEntrada(BaseModel):
    destinatario: str
    direccion: str
    ciudad: str
    provincia: str
    codigo_postal: str
    pais: str = "AR"


class ItemEntrada(BaseModel):
    external_item_id: str
    external_variant_id: str | None = None
    sku: str = Field(min_length=1, max_length=100)
    cantidad: int = Field(gt=0)
    precio_unitario: Decimal = Field(ge=0)
    descuento: Decimal = Field(default=Decimal("0"), ge=0)
    titulo: str | None = None


class PedidoEntrada(BaseModel):
    schema_version: str = "1.0"
    request_id: str | None = None
    correlation_id: str | None = None
    canal: str = "TIENDA_NUBE"
    external_order_id: str = Field(min_length=1, max_length=120)
    numero_pedido: str | None = None
    moneda: str = Field(default="ARS", min_length=3, max_length=10)
    total: Decimal = Field(ge=0)
    creado_en: datetime
    cliente: ClienteEntrada
    envio: EnvioEntrada | None = None
    items: list[ItemEntrada] = Field(min_length=1)


class WebhookTiendaNubeEntrada(BaseModel):
    store_id: str | int
    event: str
    id: str | int


async def _procesar_pedido_tienda_nube_en_segundo_plano(order_id: str) -> None:
    """Ejecuta el flujo completo con una sesión independiente de la solicitud."""

    with SessionLocal() as sesion:
        procesador = construir_procesador_pedido_tienda_nube(sesion)
        await procesador.ejecutar(order_id)


@router.post(
    "/webhooks/tienda-nube",
    status_code=status.HTTP_202_ACCEPTED,
)
async def recibir_webhook_tienda_nube(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    """Valida y encola eventos de pedidos enviados por Tiendanube."""

    configuracion = obtener_configuracion()
    cuerpo = await request.body()
    try:
        verificar_firma_webhook(
            cuerpo,
            request.headers.get("x-linkedstore-hmac-sha256"),
            configuracion.tienda_nube_webhook_secret,
        )
    except FirmaWebhookTiendaNubeInvalidaError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        entrada = WebhookTiendaNubeEntrada.model_validate_json(cuerpo)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Webhook Tiendanube inválido"
        ) from exc

    if str(entrada.store_id) != str(configuracion.tienda_nube_store_id):
        raise HTTPException(
            status_code=403, detail="El webhook pertenece a otra tienda"
        )

    evento = entrada.event.strip().lower()
    if evento not in configuracion.tienda_nube_webhook_event_list:
        return {
            "ok": True,
            "aceptado": False,
            "motivo": "EVENTO_NO_CONFIGURADO",
            "evento": evento,
        }

    if not configuracion.tienda_nube_pedidos_automaticos_habilitados:
        return {
            "ok": True,
            "aceptado": False,
            "motivo": "PROCESAMIENTO_AUTOMATICO_DESHABILITADO",
            "evento": evento,
            "order_id": str(entrada.id),
        }

    background_tasks.add_task(
        _procesar_pedido_tienda_nube_en_segundo_plano,
        str(entrada.id),
    )
    return {
        "ok": True,
        "aceptado": True,
        "evento": evento,
        "order_id": str(entrada.id),
    }


@router.post("/recibir")
def recibir_pedido(
    entrada: PedidoEntrada, db: Session = Depends(obtener_sesion_bd)
) -> dict[str, object]:
    request_id = entrada.request_id or str(uuid4())
    correlation_id = entrada.correlation_id or request_id
    pedido = PedidoExterno(
        canal=entrada.canal,
        external_order_id=entrada.external_order_id,
        numero_pedido=entrada.numero_pedido,
        moneda=entrada.moneda,
        total=entrada.total,
        creado_en=entrada.creado_en,
        cliente=ClientePedidoExterno(**entrada.cliente.model_dump()),
        envio=DireccionEnvioPedido(**entrada.envio.model_dump())
        if entrada.envio
        else None,
        items=tuple(ItemPedidoExterno(**item.model_dump()) for item in entrada.items),
        payload_crudo=entrada.model_dump(mode="json"),
    )
    resultado = RecibirPedido(RepositorioPedidos(db)).ejecutar(
        pedido, request_id, correlation_id
    )
    return {"ok": True, **resultado.__dict__}


@router.post("/tienda-nube/{order_id}/importar")
async def importar_pedido_tienda_nube(
    order_id: str,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    caso_uso = ImportarPedidoTiendaNube(
        obtener_cliente_tienda_nube(),
        RepositorioPedidos(db),
    )
    try:
        resultado = await caso_uso.ejecutar(order_id)
        return {"ok": True, **resultado.__dict__}
    except PedidoTiendaNubeNoEncontradoError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PedidoTiendaNubeInvalidoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{canal}/{external_order_id}")
def consultar_pedido(
    canal: str, external_order_id: str, db: Session = Depends(obtener_sesion_bd)
) -> dict[str, object]:
    pedido = ConsultarPedido(RepositorioPedidos(db)).ejecutar(canal, external_order_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {"ok": True, "pedido": pedido}


@router.post("/{pedido_id}/preparar-cliente-gbp")
def preparar_cliente_gbp(
    pedido_id: int,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    try:
        return PrepararClienteGBP(RepositorioPedidos(db)).ejecutar(pedido_id)
    except PedidoNoEncontradoParaClienteError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pedido_id}/crear-cliente-gbp")
async def crear_cliente_gbp(
    pedido_id: int,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    repositorio = RepositorioPedidos(db)
    caso_uso = CrearClienteGBP(
        repositorio,
        obtener_cliente_gbp_pedidos(),
        obtener_configuracion(),
    )
    try:
        resultado = await caso_uso.ejecutar(pedido_id)
        return resultado
    except PedidoNoEncontradoParaAltaClienteError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatosClienteGBPInvalidosError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EscrituraClienteGBPDeshabilitadaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AltaClienteGBPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{pedido_id}/preparar-pedido-gbp")
async def preparar_pedido_gbp(
    pedido_id: int,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    caso_uso = PrepararPedidoVentaGBP(
        RepositorioPedidos(db),
        obtener_cliente_gbp(),
        obtener_configuracion(),
    )
    try:
        return await caso_uso.ejecutar(pedido_id)
    except PedidoNoEncontradoParaPreparacionGBPError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ClienteGBPNoVinculadoError,
        ArticuloGBPNoResueltoError,
        TotalesPedidoInconsistentesError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{pedido_id}/cargar-temporal-gbp")
async def cargar_pedido_temporal_gbp(
    pedido_id: int,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    configuracion = obtener_configuracion()
    preparador = PrepararPedidoVentaGBP(
        RepositorioPedidos(db),
        obtener_cliente_gbp(),
        configuracion,
    )
    caso_uso = CargarPedidoTemporalGBP(
        preparador,
        obtener_cliente_pedido_venta_gbp(),
        configuracion,
    )
    try:
        return await caso_uso.ejecutar(pedido_id)
    except PedidoNoEncontradoParaPreparacionGBPError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ClienteGBPNoVinculadoError,
        ArticuloGBPNoResueltoError,
        TotalesPedidoInconsistentesError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CargaTemporalGBPDeshabilitadaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InsercionItemTemporalGBPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{pedido_id}/confirmar-pedido-gbp")
async def confirmar_pedido_gbp(
    pedido_id: int,
    db: Session = Depends(obtener_sesion_bd),
) -> dict[str, object]:
    configuracion = obtener_configuracion()
    repositorio = RepositorioPedidos(db)
    preparador = PrepararPedidoVentaGBP(
        repositorio, obtener_cliente_gbp(), configuracion
    )
    caso_uso = ConfirmarPedidoGBP(
        preparador, obtener_cliente_pedido_venta_gbp(), repositorio, configuracion
    )
    try:
        return await caso_uso.ejecutar(pedido_id)
    except PedidoNoEncontradoParaPreparacionGBPError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ClienteGBPNoVinculadoError,
        ArticuloGBPNoResueltoError,
        TotalesPedidoInconsistentesError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConfirmacionPedidoGBPDeshabilitadaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PedidoGBPNoConciliadoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConfirmacionPedidoGBPEnCursoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InsercionItemTemporalGBPError, ConfirmacionPedidoGBPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
