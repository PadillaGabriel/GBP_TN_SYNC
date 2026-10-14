"""Persistencia de identidad de categorías, sin confiar en referencias caducadas."""
from __future__ import annotations


class MapeoCategoriasPostgres:
    def __init__(self, *, database_url: str, store_id: str) -> None:
        if not store_id.strip():
            raise ValueError("store_id requerido")
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("Mapeo persistente requiere PostgreSQL")
        self.dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.store_id = store_id.strip()

    async def buscar(self, clave: str, parent_id: int | None) -> int | None:
        import psycopg
        async with await psycopg.AsyncConnection.connect(self.dsn, connect_timeout=10) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT tn_category_id FROM categoria_tienda_mapeos "
                    "WHERE store_id=%s AND parent_id=%s AND clave_canonica=%s",
                    (self.store_id, parent_id or 0, clave),
                )
                row = await cursor.fetchone()
                return int(row[0]) if row else None

    async def guardar(self, clave: str, parent_id: int | None, tn_id: int) -> None:
        import psycopg
        async with await psycopg.AsyncConnection.connect(self.dsn, connect_timeout=10) as conn:
            await conn.execute(
                "INSERT INTO categoria_tienda_mapeos "
                "(store_id, parent_id, clave_canonica, tn_category_id) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (store_id, parent_id, clave_canonica) "
                "DO UPDATE SET tn_category_id=EXCLUDED.tn_category_id, updated_at=now()",
                (self.store_id, parent_id or 0, clave, tn_id),
            )
            await conn.commit()
