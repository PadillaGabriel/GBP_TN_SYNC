"""Regresión: la auditoría del lote completo debe usar el export configurado."""
from types import SimpleNamespace

import pytest

from app.aplicacion.servicios.servicio_sincronizacion_stock import StockSyncService


class Productos:
    def listar_mapeos_activos_para_stock(self, *, limit):
        return [{"id_sistema_gbp": "123", "sku": "ABC"}]


class Exportaciones:
    def __init__(self):
        self.consultas = []

    async def ejecutar(self, export_id, *, usar_cache):
        self.consultas.append(export_id)
        return SimpleNamespace(filas=[{"item_id": "123", "stock_disponible": "4"}])


class Auditoria:
    def __init__(self):
        self.registros = []

    def registrar(self, **kwargs):
        self.registros.append(kwargs)


@pytest.mark.asyncio
async def test_lote_stock_completo_registra_id_configurado_sin_nameerror():
    service = StockSyncService.__new__(StockSyncService)
    service.settings = SimpleNamespace(gbp_export_productos_stock_id=14, dry_run=True)
    service.productos = Productos()
    service.exportaciones = Exportaciones()
    service.auditoria = Auditoria()

    async def simular(item, *, fila_stock):
        assert fila_stock["stock_disponible"] == "4"
        return {"estado": "SIMULADO"}

    service._sincronizar_item = simular
    resultado = await service.sincronizar_lote(limit=100)
    assert resultado["ok"] is True
    assert resultado["simulados"] == 1
    assert service.exportaciones.consultas == [14]
    assert service.auditoria.registros[0]["metodo_gbp"] == "wsExportDataById(14)"
