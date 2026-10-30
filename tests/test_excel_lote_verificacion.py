"""Verificación del lote: nunca equiparar importación con stock sincronizado."""
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencias import obtener_sesion_bd
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.repositorios.trabajos_sincronizacion import RepositorioTrabajosSincronizacion
from app.principal import create_app


def test_lote_sin_mapeo_no_aparece_sincronizado(monkeypatch):
    monkeypatch.setattr('app.principal.verificar_admin', lambda *_: None)
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    lote = 'a' * 32
    with factory() as db:
        repo = RepositorioTrabajosSincronizacion(db)
        j = repo.crear(tipo='IMPORTAR_SKU_TN', sku='SKU-1', payload={'sku': 'SKU-1', 'forzar': False, 'lote_excel': lote})
        repo.reclamar('test-worker', 60)
        repo.actualizar(j.id, estado='FINALIZADO', finalizar=True,
                        progreso={'mapeo_verificado': False, 'dry_run': False})
    app = create_app()
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[obtener_sesion_bd] = session
    with TestClient(app) as client:
        response = client.get(f'/admin/panel/importar-excel/lotes/{lote}')
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 1
        assert data['conteos']['sincronizados'] == 0
        assert data['conteos']['fallidos'] == 1
        assert data['filas'][0]['mapeado'] is False
        assert client.get('/admin/panel/importar-excel/lotes/nope').status_code == 422
        assert client.get('/admin/panel/importar-excel/lotes/' + 'b'*32).status_code == 404
    engine.dispose()
