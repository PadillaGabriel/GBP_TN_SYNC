"""Contrato del reporte 15: solo filas presentes, sin truncar movimientos."""
from types import SimpleNamespace

import pytest

from app.aplicacion.servicios.servicio_sincronizacion_stock import StockSyncService


class Exportaciones:
    def __init__(self, filas):
        self.filas = filas
        self.llamadas = []

    async def ejecutar(self, export_id, *, usar_cache):
        self.llamadas.append((export_id, usar_cache))
        return SimpleNamespace(filas=self.filas)


class Productos:
    def __init__(self, ids):
        self.ids = ids
        self.consultas = []

    def listar_mapeos_activos_para_stock_por_item_ids(self, ids, *, batch_size):
        self.consultas.append((ids, batch_size))
        return [
            {"id_sistema_gbp": str(i), "sku": f"SKU-{i}"}
            for i in self.ids if str(i) in ids
        ]


class Auditoria:
    def __init__(self):
        self.registros = []

    def registrar(self, **kwargs):
        self.registros.append(kwargs)


def crear_servicio(filas, mapeos=()):
    servicio = StockSyncService.__new__(StockSyncService)
    servicio.settings = SimpleNamespace(gbp_export_movimientos_stock_id=15, dry_run=True)
    servicio.exportaciones = Exportaciones(filas)
    servicio.productos = Productos(mapeos)
    servicio.auditoria = Auditoria()
    procesados = []

    async def sincronizar(item, *, fila_stock, export_id=None):
        assert export_id == 15
        procesados.append((item["id_sistema_gbp"], fila_stock["stock_disponible"]))
        return {"estado": "SIN_CAMBIOS"}

    servicio._sincronizar_item = sincronizar
    return servicio, procesados


@pytest.mark.asyncio
async def test_reporte_vacio_no_actualiza_ningun_articulo():
    servicio, procesados = crear_servicio([], ["1"])
    resultado = await servicio.sincronizar_incremental()
    assert resultado["ok"] is True
    assert resultado["detectados_gbp"] == 0
    assert resultado["procesados"] == 0
    assert procesados == []
    assert servicio.exportaciones.llamadas == [(15, False)]


@pytest.mark.asyncio
async def test_no_trunca_mapeos_por_batch_limit_y_ignora_no_mapeados():
    filas = [{"item_id": str(i), "stock_disponible": str(i)} for i in range(1, 5)]
    servicio, procesados = crear_servicio(filas, ["1", "2", "3"])
    resultado = await servicio.sincronizar_incremental(limit=1)
    assert resultado["detectados_gbp"] == 4
    assert resultado["seleccionados"] == 3
    assert resultado["procesados"] == 3
    assert {i for i, _ in procesados} == {"1", "2", "3"}
    assert servicio.productos.consultas == [(set(map(str, range(1, 5))), 1)]


@pytest.mark.asyncio
async def test_rechaza_exportacion_con_item_id_duplicado():
    servicio, procesados = crear_servicio([
        {"item_id": "1", "stock_disponible": "2"},
        {"item_id": "1", "stock_disponible": "3"},
    ])
    with pytest.raises(ValueError, match="duplicado"):
        await servicio.sincronizar_incremental()
    assert procesados == []


@pytest.mark.asyncio
async def test_rechaza_fila_sin_item_id():
    servicio, _ = crear_servicio([{"stock_disponible": "3"}])
    with pytest.raises(ValueError, match="vacío"):
        await servicio.sincronizar_incremental()
