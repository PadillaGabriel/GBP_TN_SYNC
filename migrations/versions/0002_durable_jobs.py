"""Durable job execution and separate progress/error storage.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reparar solamente variantes conocidas del esquema legado, bajo migración versionada.
    conn = op.get_bind()
    columns = {c["name"] for c in sa.inspect(conn).get_columns("pedidos_externos")}
    if "gbp_guid" not in columns:
        op.add_column("pedidos_externos", sa.Column("gbp_guid", sa.String(100), nullable=True))
        op.create_index("ix_pedidos_externos_gbp_guid", "pedidos_externos", ["gbp_guid"])
    if "confirmation_error" not in columns:
        op.add_column("pedidos_externos", sa.Column("confirmation_error", sa.Text(), nullable=True))
    op.add_column("sync_jobs", sa.Column("progreso_json", sa.Text(), nullable=True))
    op.add_column("sync_jobs", sa.Column("payload_json", sa.Text(), nullable=True))
    op.add_column("sync_jobs", sa.Column("error_detalle", sa.Text(), nullable=True))
    op.add_column("sync_jobs", sa.Column("idempotency_key", sa.String(240), nullable=True))
    op.add_column("sync_jobs", sa.Column("worker_id", sa.String(120), nullable=True))
    op.add_column("sync_jobs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_jobs", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.create_index("uq_sync_jobs_idempotency_key", "sync_jobs", ["idempotency_key"], unique=True)
    op.create_index("ix_sync_jobs_claim", "sync_jobs", ["estado", "prioridad", "created_at"])
    # Nunca recuperar automáticamente un job legado que pudo aplicar efectos externos.
    op.execute("UPDATE sync_jobs SET estado='REQUIERE_REVISION' WHERE estado='EN_PROCESO'")
    # Una cancelación solicitada no equivale a una cancelación confirmada.
    # Retener la incertidumbre operativa y exigir conciliación manual.
    op.execute("UPDATE sync_jobs SET estado='REQUIERE_REVISION' WHERE estado='CANCELACION_SOLICITADA'")
    op.execute("UPDATE sync_jobs SET progreso_json=error_mensaje WHERE error_mensaje LIKE '{%'")


def downgrade() -> None:
    op.drop_index("ix_sync_jobs_claim", table_name="sync_jobs")
    op.drop_index("uq_sync_jobs_idempotency_key", table_name="sync_jobs")
    for name in ("updated_at", "heartbeat_at", "lease_until", "worker_id", "idempotency_key", "error_detalle", "payload_json", "progreso_json"):
        op.drop_column("sync_jobs", name)
