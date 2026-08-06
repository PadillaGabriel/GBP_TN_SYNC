from __future__ import annotations

from decimal import Decimal

import pytest

from app.infraestructura.gbp.exportaciones import (
    ErrorExportacionGBP,
    ProveedorExportacionesGBP,
    detectar_error_generacion,
)


class ClienteExportacionFalso:
    def __init__(self, filas: list[dict[str, str]]) -> None:
        self.filas = filas
        self.llamadas = 0

    async def obtener_exportacion(self, export_id: int) -> list[dict[str, str]]:
        del export_id
        self.llamadas += 1
        return self.filas


def test_detecta_generation_error_sin_importar_fila_como_producto() -> None:
    filas = [{"GenerationError": "Invalid column name"}]

    assert detectar_error_generacion(filas) == "Invalid column name"


@pytest.mark.asyncio
async def test_ejecutar_rechaza_generation_error() -> None:
    cliente = ClienteExportacionFalso([{"GenerationError": "Consulta inválida"}])
    proveedor = ProveedorExportacionesGBP(cliente)  # type: ignore[arg-type]

    with pytest.raises(ErrorExportacionGBP, match="Consulta inválida"):
        await proveedor.ejecutar(12, usar_cache=False)


@pytest.mark.asyncio
async def test_buscar_fila_prioriza_item_code_operativo() -> None:
    cliente = ClienteExportacionFalso(
        [
            {"item_id": "9798", "item_code": "8082"},
            {"item_id": "100", "item_code": "ABC-1"},
        ]
    )
    proveedor = ProveedorExportacionesGBP(cliente)  # type: ignore[arg-type]

    fila = await proveedor.buscar_fila(12, item_code=" abc-1 ", usar_cache=False)

    assert fila == {"item_id": "100", "item_code": "ABC-1"}


def test_producto_general_no_inventa_precio_ni_stock() -> None:
    from app.infraestructura.gbp.exportaciones import producto_desde_exportacion

    producto = producto_desde_exportacion(
        {
            "item_id": "9798",
            "item_code": "8082",
            "item_desc": "BANDEJA",
            "item_active": "true",
            "item_web": "true",
        }
    )

    assert producto.precio_importado is None
    assert producto.stock is None


def test_precio_cero_se_conserva_como_precio_informado() -> None:
    from app.infraestructura.gbp.exportaciones import precio_desde_exportacion

    precio = precio_desde_exportacion(
        {"item_id": "9798", "item_code": "8082", "precio_final": "0"},
        lista_precio_id="4",
    )

    assert precio is not None
    assert precio.monto == Decimal("0")
