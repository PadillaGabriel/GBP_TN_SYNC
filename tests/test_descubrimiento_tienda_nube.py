"""Regresiones de vinculación defensiva: no crea contenido externo."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.aplicacion.servicios.descubrimiento_tienda_nube import DescubrimientoTiendaNube
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.modelos import ProductoFuenteModel, ProductoTiendaNubeModel


class FakeTN:
    def __init__(self, paginas):
        self.paginas = paginas

    async def get_products_page(self, *, page, per_page=100):
        return self.paginas.get(page, [])

    async def get_product_by_sku(self, sku):
        return next((p for rows in self.paginas.values() for p in rows if any(
            v.get("sku") == sku for v in p.get("variants", [])
        )), None)


def build(paginas):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ProductoFuenteModel(id_sistema_gbp="120", sku="SKU-120", titulo="Producto GBP"))
    db.commit()
    return db, engine, DescubrimientoTiendaNube(db=db, tn=FakeTN(paginas))


async def test_descubre_productos_publicados_directamente_en_tn():
    db, engine, service = build({1: [{"id": 23, "variants": [{"id": 65, "sku": "SKU-120"}]}]})
    try:
        summary = await service.recorrer_catalogo()
        assert summary["vinculados"] == 1
        row = db.query(ProductoTiendaNubeModel).one()
        assert (row.tn_product_id, row.tn_variant_id) == ("23", "65")
        assert (await service.recorrer_catalogo())["ya_vinculados"] == 1
    finally:
        db.close(); engine.dispose()


async def test_sku_duplicado_no_crea_mapeo():
    db, engine, service = build({1: [
        {"id": 23, "variants": [{"id": 65, "sku": "SKU-120"}]},
        {"id": 24, "variants": [{"id": 66, "sku": "SKU-120"}]},
    ]})
    try:
        summary = await service.recorrer_catalogo()
        assert summary["conflictos"] == 1
        assert db.query(ProductoTiendaNubeModel).count() == 0
    finally:
        db.close(); engine.dispose()


async def test_catalogo_incompleto_no_escribe_mapeos():
    db, engine, service = build({1: [
        {"id": j, "variants": [{"id": j, "sku": "SKU-120" if j == 1 else f"X-{j}"}]}
        for j in range(1, 101)
    ]})
    try:
        summary = await service.recorrer_catalogo(max_pages=1)
        assert summary["incompleto"] is True
        assert db.query(ProductoTiendaNubeModel).count() == 0
    finally:
        db.close(); engine.dispose()


async def test_no_sobrescribe_mapeo_activo_conflictivo():
    db, engine, service = build({1: [{"id": 99, "variants": [{"id": 88, "sku": "SKU-120"}]}]})
    try:
        source = db.query(ProductoFuenteModel).one()
        db.add(ProductoTiendaNubeModel(producto_fuente_id=source.id, sku="SKU-120", tn_product_id="23", tn_variant_id="65", estado_publicacion="activo"))
        db.commit()
        summary = await service.recorrer_catalogo()
        assert summary["conflictos"] == 1
        assert db.query(ProductoTiendaNubeModel).one().tn_product_id == "23"
    finally:
        db.close(); engine.dispose()
