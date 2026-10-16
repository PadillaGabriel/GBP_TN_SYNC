"""Pruebas reales del repositorio SQL invocado por STOCK_SYNC_INCREMENTAL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.modelos import (
    ProductoFuenteModel,
    ProductoTiendaNubeModel,
    StockActualModel,
)
from app.infraestructura.persistencia.repositorios.productos import RepositorioProductos


def test_mapeos_por_item_id_no_trunca_y_filtra_inactivos():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for numero, estado in [(1, "activo"), (2, "activo"), (3, "eliminado_tn")]:
            p = ProductoFuenteModel(id_sistema_gbp=str(numero), sku=f"SKU-{numero}", titulo="Test")
            db.add(p)
            db.flush()
            db.add(ProductoTiendaNubeModel(producto_fuente_id=p.id, sku=p.sku, tn_product_id=str(numero), estado_publicacion=estado))
            db.add(StockActualModel(producto_fuente_id=p.id, sku=p.sku, stor_id=18, stock_disponible_gbp=4, usado_para_tienda_nube=True))
        db.commit()
        repo = RepositorioProductos(db)
        rows = repo.listar_mapeos_activos_para_stock_por_item_ids({"1", "2", "3", "999"}, batch_size=1)
        assert {r["id_sistema_gbp"] for r in rows} == {"1", "2"}
        assert all("tn_product_id" in r and "stock_publicable_tn" in r for r in rows)
        assert repo.listar_mapeos_activos_para_stock_por_item_ids(set()) == []
