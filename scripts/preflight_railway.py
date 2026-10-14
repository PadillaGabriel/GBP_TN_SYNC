"""Preflight READ-ONLY previo a Alembic stamp/upgrade sobre Railway.

No modifica esquema, no imprime credenciales ni datos personales.
Uso: python -m scripts.preflight_railway
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, select, text

from app.infraestructura.persistencia.base_datos import engine

TABLES_REQUIRED = {"sync_jobs", "pedidos_externos", "productos_fuente", "productos_tienda_nube"}
JOB_COLUMNS_REQUIRED = {
    "id", "tipo", "estado", "sku", "prioridad", "intentos", "error_codigo",
    "error_mensaje", "created_at", "started_at", "finished_at",
}


def main() -> int:
    if engine.dialect.name != "postgresql":
        print("BLOQUEADO: para el corte de Railway se exige conexión PostgreSQL.")
        return 2
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        versioned = "alembic_version" in tables
        existing = tables & TABLES_REQUIRED
        print(f"Tablas reconocidas: {len(existing)}/{len(TABLES_REQUIRED)}. Alembic versionado: {versioned}")
        if not existing:
            print("Esquema vacío: una vez respaldado, corresponde alembic upgrade head (NO stamp).")
            return 0
        missing = TABLES_REQUIRED - tables
        if missing:
            print("BLOQUEADO: faltan tablas del esquema legado: " + ", ".join(sorted(missing)))
            return 3
        job_columns = {col["name"] for col in inspector.get_columns("sync_jobs")}
        missing_columns = JOB_COLUMNS_REQUIRED - job_columns
        if missing_columns:
            print("BLOQUEADO: sync_jobs incompatible: " + ", ".join(sorted(missing_columns)))
            return 4
        states = connection.execute(
            text("SELECT estado, COUNT(*) FROM sync_jobs GROUP BY estado")
        ).all()
        count = sum(count for state, count in states if state in {"EN_PROCESO", "CANCELACION_SOLICITADA"})
        print(f"Jobs activos antes del corte: {count}")
        if count:
            print("BLOQUEADO: detener origen, esperar fin o conciliar jobs antes de migrar.")
            return 5
        if versioned:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            print(f"Revisión Alembic actual: {revision}")
            if revision not in ("0001", "0002"):
                print("BLOQUEADO: revisión inesperada; requiere revisión de DBA.")
                return 6
        else:
            # El sello requiere validación del DBA; no efectuar cambios implícitos.
            print("ESQUEMA LEGADO: revisar contra baseline 0001, respaldar y solo entonces ejecutar alembic stamp 0001.")
        print("Preflight básico correcto; NO acredita backups, seguridad ni equivalencia funcional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
