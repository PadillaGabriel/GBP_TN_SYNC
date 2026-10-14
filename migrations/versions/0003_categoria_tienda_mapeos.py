"""Mapeo canónico GBP → ID de categoría Tiendanube por tienda y padre.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categoria_tienda_mapeos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("clave_canonica", sa.String(240), nullable=False),
        sa.Column("tn_category_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "parent_id", "clave_canonica", name="uq_categoria_tienda_mapeo_identidad"),
    )


def downgrade() -> None:
    op.drop_table("categoria_tienda_mapeos")
