"""Regresión de las pantallas operativas contra una base local aislada."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencias import obtener_sesion_bd
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.modelos import SyncAuditModel
from app.infraestructura.persistencia.repositorios.auditoria_sincronizacion import (
    RepositorioAuditoriaSincronizacion,
)
from app.principal import create_app


@pytest.fixture
def ui_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_auditoria_listar_recientes_acotada_y_descendente(ui_database):
    with ui_database() as db:
        db.add_all(
            [
                SyncAuditModel(
                    sku=f"SKU-{idx}",
                    accion="AUDITAR_SKU",
                    estado="OK",
                    mensaje="Completada",
                    created_at=datetime(2026, 10, 14, idx, 0, tzinfo=UTC),
                )
                for idx in range(1, 5)
            ]
        )
        db.commit()
        repo = RepositorioAuditoriaSincronizacion(db)
        rows = repo.listar_recientes(limit=2)
        assert len(rows) == 2
        assert [item["sku"] for item in rows] == ["SKU-4", "SKU-3"]
        assert all("created_at" in row for row in rows)
        with pytest.raises(ValueError):
            repo.listar_recientes(limit=1000)


@pytest.mark.parametrize(
    "route, expected",
    [
        ("/admin/panel", "Centro de operaciones"),
        ("/admin/panel/productos", "Catálogo de productos"),
        ("/admin/panel/categorias", "Normalización de categorías"),
        ("/admin/panel/importaciones", "Importación y publicación"),
        ("/admin/panel/sincronizacion", "Sincronización"),
        ("/admin/panel/pedidos", "Pedidos Tiendanube"),
        ("/admin/panel/trabajos", "Centro de trabajos"),
        ("/admin/panel/auditoria", "Auditoría y trazabilidad"),
        ("/admin/panel/exportaciones", "Exportaciones GBP"),
        ("/admin/panel/configuracion", "Configuración operativa"),
    ],
)
def test_paginas_ui_responden_sin_servicios_externos(
    ui_database, monkeypatch, route, expected
):
    monkeypatch.setattr("app.principal.verificar_admin", lambda *_: None)
    api = create_app()

    def sesion_test():
        with ui_database() as db:
            yield db

    api.dependency_overrides[obtener_sesion_bd] = sesion_test
    with TestClient(api) as client:
        result = client.get(route)
    assert result.status_code == 200
    assert expected in result.text
    assert 'id="mainContent"' in result.text
    assert 'id="themeToggle"' in result.text
    assert 'id="sidebarBackdrop"' in result.text


def test_trabajos_ui_tiene_inspeccion_y_filtros(ui_database, monkeypatch):
    monkeypatch.setattr("app.principal.verificar_admin", lambda *_: None)
    api = create_app()

    def sesion_test():
        with ui_database() as db:
            yield db

    api.dependency_overrides[obtener_sesion_bd] = sesion_test
    with TestClient(api) as client:
        response = client.get("/admin/panel/trabajos")
    assert response.status_code == 200
    for expected in (
        'id="jobSearch"',
        'id="jobStateFilter"',
        'id="jobDetailDialog"',
        'data-job-state-metric="REQUIERE_REVISION"',
    ):
        assert expected in response.text


def test_sincronizacion_ui_tiene_modal_de_detalle_en_la_misma_pantalla(ui_database, monkeypatch):
    monkeypatch.setattr("app.principal.verificar_admin", lambda *_: None)
    api = create_app()

    def sesion_test():
        with ui_database() as db:
            yield db

    api.dependency_overrides[obtener_sesion_bd] = sesion_test
    with TestClient(api) as client:
        response = client.get("/admin/panel/sincronizacion")
    assert response.status_code == 200
    for expected in (
        'id="jobDetailDialog"',
        'id="jobDetailContent"',
        'Últimos trabajos de sincronización',
    ):
        assert expected in response.text


def test_sin_modulos_ui_muertos_ni_fuentes_remotas():
    base = Path(__file__).resolve().parents[1] / "app/static/enterprise"
    source = (base / "app.js").read_text(encoding="utf-8")
    style = (base / "app.css").read_text(encoding="utf-8")
    assert "confirmations.js" not in source
    assert not (base / "features/confirmations.js").exists()
    assert "fonts.googleapis.com" not in style
    assert "prefers-reduced-motion" in style


def test_sincronizacion_fecha_legible_y_detalle_local():
    root = Path(__file__).resolve().parents[1]
    template = (root / "app/templates/enterprise/sincronizacion.html").read_text(encoding="utf-8")
    controls = (root / "app/static/enterprise/features/sync-controls.js").read_text(encoding="utf-8")
    jobs = (root / "app/static/enterprise/features/jobs.js").read_text(encoding="utf-8")
    assert 'data-sync-timestamp=' in template
    assert "Intl.DateTimeFormat('es-AR'" in controls
    assert 'data-job-detail="{{ job.id }}"' in template
    assert 'id="jobDetailDialog"' in template
    assert 'initializeJobInteractions();' in jobs
    assert '/admin/panel/trabajos?focus={{ job.id }}' not in template
