from __future__ import annotations

from decimal import Decimal

import pytest

from app.aplicacion.importacion_productos.compositor_producto_exportaciones import (
    CompositorProductoExportacionesGBP,
    ConfiguracionExportacionesProducto,
)
from app.dominio.errores import DatoIncompletoError
from app.infraestructura.gbp.exportaciones import ProveedorExportacionesGBP


class ClientePorExportacionFalso:
    def __init__(self, respuestas: dict[int, list[dict[str, str]]]) -> None:
        self.respuestas = respuestas
        self.llamadas: list[int] = []

    async def obtener_exportacion(self, export_id: int) -> list[dict[str, str]]:
        self.llamadas.append(export_id)
        return self.respuestas.get(export_id, [])


def crear_compositor(
    respuestas: dict[int, list[dict[str, str]]],
) -> CompositorProductoExportacionesGBP:
    cliente = ClientePorExportacionFalso(respuestas)
    proveedor = ProveedorExportacionesGBP(cliente, cache_seconds=120)  # type: ignore[arg-type]
    return CompositorProductoExportacionesGBP(
        proveedor,
        ConfiguracionExportacionesProducto(
            productos_general_id=12,
            precios_id=13,
            stock_id=14,
            lista_precio_id="4",
            deposito_id="18",
        ),
    )


@pytest.mark.asyncio
async def test_compone_producto_desde_tres_exportaciones() -> None:
    compositor = crear_compositor(
        {
            12: [
                {
                    "item_id": "9798",
                    "item_code": "8082",
                    "item_desc": "BANDEJA",
                    "item_active": "true",
                    "item_web": "true",
                }
            ],
            13: [
                {
                    "item_id": "9798",
                    "item_code": "8082",
                    "precio_final": "1234.50",
                }
            ],
            14: [
                {
                    "item_id": "9798",
                    "item_code": "8082",
                    "item_active": "true",
                    "item_web": "true",
                    "stock_disponible": "7",
                }
            ],
        }
    )

    producto = await compositor.obtener_por_sku("8082")

    assert producto.precio_importado is not None
    assert producto.precio_importado.monto == Decimal("1234.50")
    assert producto.stock is not None
    assert producto.stock.cantidad == 7
    assert producto.stock.depositos[0].stor_id == "18"
    assert producto.payload_crudo is not None
    assert producto.payload_crudo["general"]["item_id"] == "9798"


@pytest.mark.asyncio
async def test_fila_stock_ausente_no_se_convierte_en_stock_cero() -> None:
    compositor = crear_compositor(
        {
            12: [{"item_id": "9798", "item_code": "8082", "item_desc": "X"}],
            13: [{"item_id": "9798", "item_code": "8082", "precio_final": "10"}],
            14: [],
        }
    )

    producto = await compositor.obtener_por_sku("8082")

    assert producto.stock is None


@pytest.mark.asyncio
async def test_stock_cero_real_se_conserva_como_cero() -> None:
    compositor = crear_compositor(
        {
            12: [{"item_id": "9798", "item_code": "8082", "item_desc": "X"}],
            13: [],
            14: [
                {
                    "item_id": "9798",
                    "item_code": "8082",
                    "item_active": "true",
                    "item_web": "true",
                    "stock_disponible": "0",
                }
            ],
        }
    )

    producto = await compositor.obtener_por_sku("8082")

    assert producto.stock is not None
    assert producto.stock.cantidad == 0


@pytest.mark.asyncio
async def test_producto_no_web_lleva_stock_a_cero() -> None:
    compositor = crear_compositor(
        {
            12: [{"item_id": "9798", "item_code": "8082", "item_desc": "X"}],
            13: [],
            14: [
                {
                    "item_id": "9798",
                    "item_code": "8082",
                    "item_active": "true",
                    "item_web": "false",
                    "stock_disponible": "15",
                }
            ],
        }
    )

    producto = await compositor.obtener_por_sku("8082")

    assert producto.publicable_web is False
    assert producto.stock is not None
    assert producto.stock.cantidad == 0
    assert producto.stock.stock_original_gbp == 15.0


@pytest.mark.asyncio
async def test_rechaza_discrepancia_de_identidad() -> None:
    compositor = crear_compositor(
        {
            12: [{"item_id": "9798", "item_code": "8082", "item_desc": "X"}],
            13: [{"item_id": "9999", "item_code": "8082", "precio_final": "10"}],
            14: [],
        }
    )

    with pytest.raises(DatoIncompletoError, match="item_id=9999"):
        await compositor.obtener_por_sku("8082")


@pytest.mark.asyncio
async def test_precio_cero_se_conserva_como_fila_informada() -> None:
    compositor = crear_compositor(
        {
            12: [{"item_id": "10", "item_code": "SKU10", "item_desc": "X"}],
            13: [{"item_id": "10", "item_code": "SKU10", "precio_final": "0.00"}],
            14: [
                {
                    "item_id": "10",
                    "item_code": "SKU10",
                    "item_active": "true",
                    "item_web": "true",
                    "stock_disponible": "5",
                }
            ],
        }
    )

    producto = await compositor.obtener_por_sku("SKU10")

    assert producto.precio_importado is not None
    assert producto.precio_importado.monto == Decimal("0.00")
    assert producto.requiere_consultar_precio is True
