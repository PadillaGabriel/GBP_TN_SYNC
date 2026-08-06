from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.aplicacion.pedidos.modelos import ResultadoRecepcionPedido
from app.dominio.pedidos import (
    EstadoIntegracionPedido,
    EstadoNegocioPedido,
    EtapaProcesamientoPedido,
    PedidoExterno,
)
from app.infraestructura.persistencia.modelos import (
    PedidoEstadoHistorialModel,
    PedidoExternoItemModel,
    PedidoExternoModel,
)


class RepositorioPedidos:
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def recibir_idempotente(
        self, pedido: PedidoExterno, request_id: str, correlation_id: str
    ) -> ResultadoRecepcionPedido:
        canal = pedido.canal.strip().upper()
        external_order_id = pedido.external_order_id.strip()
        existente = self._buscar(canal, external_order_id)
        if existente is not None:
            return self._resultado(existente, creado=False)

        modelo = PedidoExternoModel(
            canal=canal,
            external_order_id=external_order_id,
            numero_pedido=pedido.numero_pedido,
            moneda=pedido.moneda.upper(),
            total=pedido.total,
            creado_en_origen=pedido.creado_en,
            cliente_json=json.dumps(
                asdict(pedido.cliente), ensure_ascii=False, default=str
            ),
            envio_json=json.dumps(asdict(pedido.envio), ensure_ascii=False, default=str)
            if pedido.envio
            else None,
            payload_crudo=json.dumps(
                pedido.payload_crudo, ensure_ascii=False, default=str
            ),
            estado_negocio=EstadoNegocioPedido.RECIBIDO,
            estado_integracion=EstadoIntegracionPedido.PENDIENTE,
            etapa=EtapaProcesamientoPedido.RECIBIDO,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        modelo.items = [
            PedidoExternoItemModel(
                external_item_id=item.external_item_id,
                external_variant_id=item.external_variant_id,
                sku=item.sku.strip(),
                titulo=item.titulo,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                descuento=item.descuento,
            )
            for item in pedido.items
        ]
        modelo.historial = [
            PedidoEstadoHistorialModel(
                estado_negocio=EstadoNegocioPedido.RECIBIDO,
                estado_integracion=EstadoIntegracionPedido.PENDIENTE,
                etapa=EtapaProcesamientoPedido.RECIBIDO,
                motivo="Pedido recibido y persistido de forma idempotente",
            )
        ]
        self._sesion.add(modelo)
        try:
            self._sesion.commit()
            self._sesion.refresh(modelo)
            return self._resultado(modelo, creado=True)
        except IntegrityError:
            self._sesion.rollback()
            existente = self._buscar(canal, external_order_id)
            if existente is None:
                raise
            return self._resultado(existente, creado=False)

    def obtener_por_clave(
        self, canal: str, external_order_id: str
    ) -> dict[str, object] | None:
        modelo = self._sesion.scalar(
            select(PedidoExternoModel)
            .options(
                selectinload(PedidoExternoModel.items),
                selectinload(PedidoExternoModel.historial),
            )
            .where(
                PedidoExternoModel.canal == canal,
                PedidoExternoModel.external_order_id == external_order_id,
            )
        )
        if modelo is None:
            return None
        return {
            "id": modelo.id,
            "canal": modelo.canal,
            "external_order_id": modelo.external_order_id,
            "numero_pedido": modelo.numero_pedido,
            "moneda": modelo.moneda,
            "total": str(modelo.total),
            "estado_negocio": modelo.estado_negocio,
            "estado_integracion": modelo.estado_integracion,
            "etapa": modelo.etapa,
            "gbp_order_id": modelo.gbp_order_id,
            "gbp_guid": modelo.gbp_guid,
            "confirmation_error": modelo.confirmation_error,
            "items": [
                {
                    "sku": item.sku,
                    "cantidad": item.cantidad,
                    "precio_unitario": str(item.precio_unitario),
                }
                for item in modelo.items
            ],
            "created_at": modelo.created_at.isoformat() if modelo.created_at else None,
        }

    def obtener_por_id_para_validacion(
        self, pedido_id: int
    ) -> dict[str, object] | None:
        modelo = self._sesion.scalar(
            select(PedidoExternoModel)
            .options(selectinload(PedidoExternoModel.items))
            .where(PedidoExternoModel.id == pedido_id)
        )
        if modelo is None:
            return None

        try:
            cliente = json.loads(modelo.cliente_json or "{}")
        except json.JSONDecodeError:
            cliente = {}

        try:
            envio = json.loads(modelo.envio_json or "{}")
        except json.JSONDecodeError:
            envio = {}

        try:
            payload_crudo = json.loads(modelo.payload_crudo or "{}")
        except json.JSONDecodeError:
            payload_crudo = {}

        return {
            "id": modelo.id,
            "canal": modelo.canal,
            "external_order_id": modelo.external_order_id,
            "numero_pedido": modelo.numero_pedido,
            "moneda": modelo.moneda,
            "total": str(modelo.total),
            "correlation_id": modelo.correlation_id,
            "cliente": cliente,
            "envio": envio,
            "payload_crudo": payload_crudo,
            "items": [
                {
                    "external_item_id": item.external_item_id,
                    "external_variant_id": item.external_variant_id,
                    "sku": item.sku.strip(),
                    "quantity": item.cantidad,
                    "unit_price": str(item.precio_unitario),
                    "discount": str(item.descuento),
                    "title": item.titulo,
                }
                for item in modelo.items
            ],
        }

    def vincular_cliente_gbp(self, pedido_id: int, cust_id: int) -> None:
        modelo = self._sesion.get(PedidoExternoModel, pedido_id)
        if modelo is None:
            raise LookupError(f"Pedido {pedido_id} no encontrado")
        try:
            cliente = json.loads(modelo.cliente_json or "{}")
        except json.JSONDecodeError:
            cliente = {}
        cliente["gbp_customer_id"] = int(cust_id)
        modelo.cliente_json = json.dumps(cliente, ensure_ascii=False, default=str)
        modelo.etapa = "CLIENTE_GBP_RESUELTO"
        modelo.historial.append(
            PedidoEstadoHistorialModel(
                estado_negocio=modelo.estado_negocio,
                estado_integracion=modelo.estado_integracion,
                etapa=modelo.etapa,
                motivo=f"Cliente GBP vinculado: cust_id={cust_id}",
            )
        )
        self._sesion.commit()

    def obtener_gbp_guid(self, pedido_id: int) -> str | None:
        modelo = self._sesion.get(PedidoExternoModel, pedido_id)
        if modelo is None:
            raise LookupError(f"Pedido {pedido_id} no encontrado")
        return str(modelo.gbp_guid).strip() if modelo.gbp_guid else None

    def iniciar_confirmacion_gbp(self, pedido_id: int) -> bool:
        """Reserva atómicamente la confirmación para una sola ejecución."""
        resultado = self._sesion.execute(
            update(PedidoExternoModel)
            .where(
                PedidoExternoModel.id == pedido_id,
                PedidoExternoModel.gbp_order_id.is_(None),
                PedidoExternoModel.estado_integracion != "CONFIRMANDO_GBP",
            )
            .values(
                estado_integracion="CONFIRMANDO_GBP",
                etapa="CONFIRMANDO_PEDIDO_GBP",
                confirmation_error=None,
            )
        )
        if resultado.rowcount == 0:
            self._sesion.rollback()
            if self._sesion.get(PedidoExternoModel, pedido_id) is None:
                raise LookupError(f"Pedido {pedido_id} no encontrado")
            return False
        self._sesion.commit()
        return True

    def cancelar_confirmacion_gbp(self, pedido_id: int, motivo: str) -> None:
        modelo = self._sesion.get(PedidoExternoModel, pedido_id)
        if modelo is None or modelo.gbp_order_id:
            return
        modelo.estado_integracion = EstadoIntegracionPedido.ERROR_TECNICO
        modelo.etapa = "ERROR_CONFIRMACION_GBP"
        modelo.confirmation_error = str(motivo)[:2000]
        modelo.historial.append(
            PedidoEstadoHistorialModel(
                estado_negocio=modelo.estado_negocio,
                estado_integracion=modelo.estado_integracion,
                etapa=modelo.etapa,
                motivo=f"Confirmación GBP cancelada: {modelo.confirmation_error}",
            )
        )
        self._sesion.commit()

    def obtener_gbp_order_id(self, pedido_id: int) -> str | None:
        modelo = self._sesion.get(PedidoExternoModel, pedido_id)
        if modelo is None:
            raise LookupError(f"Pedido {pedido_id} no encontrado")
        return str(modelo.gbp_order_id).strip() if modelo.gbp_order_id else None

    def confirmar_pedido_gbp(
        self, pedido_id: int, gbp_order_id: str, guid: str
    ) -> None:
        modelo = self._sesion.get(PedidoExternoModel, pedido_id)
        if modelo is None:
            raise LookupError(f"Pedido {pedido_id} no encontrado")
        existente = str(modelo.gbp_order_id or "").strip()
        if existente and existente != str(gbp_order_id):
            raise RuntimeError(
                f"Pedido {pedido_id} ya vinculado al pedido GBP {existente}; se rechazo reemplazo por {gbp_order_id}"
            )
        modelo.gbp_order_id = str(gbp_order_id)
        modelo.gbp_guid = str(guid)
        modelo.confirmation_error = None
        modelo.estado_integracion = EstadoIntegracionPedido.CONFIRMADO
        modelo.etapa = "PEDIDO_GBP_CONFIRMADO"
        modelo.historial.append(
            PedidoEstadoHistorialModel(
                estado_negocio=modelo.estado_negocio,
                estado_integracion=modelo.estado_integracion,
                etapa=modelo.etapa,
                motivo=f"Pedido GBP confirmado: soh_id={gbp_order_id}, guid={guid}",
            )
        )
        self._sesion.commit()

    def _buscar(self, canal: str, external_order_id: str) -> PedidoExternoModel | None:
        return self._sesion.scalar(
            select(PedidoExternoModel).where(
                PedidoExternoModel.canal == canal,
                PedidoExternoModel.external_order_id == external_order_id,
            )
        )

    @staticmethod
    def _resultado(
        modelo: PedidoExternoModel, creado: bool
    ) -> ResultadoRecepcionPedido:
        return ResultadoRecepcionPedido(
            pedido_id=modelo.id,
            canal=modelo.canal,
            external_order_id=modelo.external_order_id,
            creado=creado,
            idempotente=not creado,
            estado_negocio=modelo.estado_negocio,
            estado_integracion=modelo.estado_integracion,
            etapa=modelo.etapa,
        )
