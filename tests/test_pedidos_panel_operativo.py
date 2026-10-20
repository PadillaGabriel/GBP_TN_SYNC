"""Regresión de lectura y seguridad del historial de pedidos."""
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.aplicacion.pedidos.casos_uso import RecibirPedido
from app.dependencias import obtener_sesion_bd
from app.dominio.pedidos import ClientePedidoExterno, ItemPedidoExterno, PedidoExterno
from app.infraestructura.persistencia.base_datos import Base
from app.infraestructura.persistencia.repositorios.pedidos import RepositorioPedidos
from app.principal import create_app


def test_historial_pedidos_y_detalle_sin_datos_personales(monkeypatch):
    monkeypatch.setattr("app.principal.verificar_admin", lambda *_: None)
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        origen = PedidoExterno(
            canal="TIENDA_NUBE", external_order_id="ORDER-987", numero_pedido="TN-987",
            moneda="ARS", total=Decimal("320"), creado_en=datetime.now(UTC),
            cliente=ClientePedidoExterno(external_customer_id="c987", nombre="Ejemplo", apellido="Privado", email="privado@example.com"),
            items=(ItemPedidoExterno("item1", "variant1", "SKU-987", 2, Decimal("160")),),
            payload_crudo={"private_token": "NO_DEBE_APARECER"},
        )
        saved = RecibirPedido(RepositorioPedidos(db)).ejecutar(origen, "req-987", "corr-987")
        repo = RepositorioPedidos(db)
        repo.vincular_cliente_gbp(saved.pedido_id, 456)
        repo.confirmar_pedido_gbp(saved.pedido_id, "789", "guid-test")

    app = create_app()
    def test_session():
        with factory() as db:
            yield db
    app.dependency_overrides[obtener_sesion_bd] = test_session
    with TestClient(app) as client:
        panel = client.get("/admin/panel/pedidos")
        assert panel.status_code == 200
        assert "Historial de integración" in panel.text
        assert "pedidos.css?v=1" in panel.text
        history = client.get("/pedidos/operaciones/historial", params={"busqueda": "789"})
        assert history.status_code == 200
        assert history.json()["total"] == 1
        record = history.json()["items"][0]
        assert record["confirmado_gbp"] is True
        assert record["gbp_order_id"] == "789"
        latest = client.get("/pedidos/operaciones/historial").json()["ultimo_confirmado"]
        assert latest["id"] == saved.pedido_id
        detail = client.get(f"/pedidos/operaciones/{saved.pedido_id}/detalle")
        assert detail.status_code == 200
        assert detail.json()["pedido"]["gbp_customer_id"] == 456
        assert len(detail.json()["pedido"]["historial"]) >= 3
        assert "privado@example.com" not in detail.text
        assert "NO_DEBE_APARECER" not in detail.text
        assert client.get("/pedidos/operaciones/99999/detalle").status_code == 404
        assert client.get("/pedidos/operaciones/historial?limit=101").status_code == 422
    engine.dispose()


def test_procesamiento_manual_bloqueado_sin_habilitacion(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("app.principal.verificar_admin", lambda *_: None)
    monkeypatch.setattr(
        "app.presentacion.rutas_pedidos.obtener_configuracion",
        lambda: SimpleNamespace(
            pedidos_escritura_gbp_habilitada=False,
            pedidos_gbp_staging_enabled=False,
            pedidos_gbp_confirmation_enabled=False,
            dry_run=True,
        ),
    )
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/pedidos/tienda-nube/52271/procesar-gbp")
    assert response.status_code == 409
    assert "deshabilitado" in response.json()["detail"]
