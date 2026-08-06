from __future__ import annotations

from app.aplicacion.puertos.repositorio_pedidos import RepositorioPedidosPuerto


class PedidoNoEncontradoParaClienteError(LookupError):
    pass


class PrepararClienteGBP:
    """Construye una propuesta de alta de cliente sin escribir en GBP."""

    def __init__(self, repositorio: RepositorioPedidosPuerto) -> None:
        self._repositorio = repositorio

    def ejecutar(self, pedido_id: int) -> dict[str, object]:
        pedido = self._repositorio.obtener_por_id_para_validacion(pedido_id)
        if pedido is None:
            raise PedidoNoEncontradoParaClienteError(
                f"Pedido {pedido_id} no encontrado"
            )

        cliente = pedido.get("cliente") or {}
        envio = pedido.get("envio") or {}
        nombre = " ".join(
            parte
            for parte in (
                str(cliente.get("nombre") or "").strip(),
                str(cliente.get("apellido") or "").strip(),
            )
            if parte
        ).strip()

        return {
            "ok": True,
            "pedido_id": pedido_id,
            "modo": "SOLO_LECTURA",
            "requiere_confirmacion": True,
            "regla_fiscal_aplicada": "CONSUMIDOR_FINAL_POR_DEFECTO_CONTROLADO",
            "cliente_propuesto": {
                "nombre": nombre or "Cliente Tienda Nube",
                "documento": cliente.get("numero_documento"),
                "tipo_documento": cliente.get("tipo_documento") or "DNI",
                "clase_fiscal_id": 2,
                "documento_facturacion_id": 145,
                "email": cliente.get("email"),
                "telefono": cliente.get("telefono"),
                "direccion": envio.get("direccion"),
                "ciudad": envio.get("ciudad"),
                "provincia": envio.get("provincia"),
                "codigo_postal": envio.get("codigo_postal"),
                "pais": envio.get("pais") or "AR",
                "lista_precio_id": 4,
                "deposito_id": 18,
            },
        }
