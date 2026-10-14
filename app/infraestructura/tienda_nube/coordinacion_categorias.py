"""Coordinación de altas de categorías entre procesos y réplicas Railway.

Serializa únicamente la resolución/creación de categorías de una tienda.
No mantiene transacciones de negocio abiertas ni crea tablas auxiliares.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import hashlib



class CoordinadorCategoriasPostgres:
    def __init__(self, *, database_url: str, store_id: str) -> None:
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("La coordinación distribuida requiere PostgreSQL")
        if not store_id.strip():
            raise ValueError("Se requiere el identificador de tienda")
        self._dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        # Clave fija por tienda, idéntica entre todos los workers.
        digest = hashlib.blake2b(f"gbp-tn:categorias:{store_id}".encode(), digest_size=8).digest()
        self._lock_id = int.from_bytes(digest, "big", signed=True)

    @asynccontextmanager
    async def proteger(self) -> AsyncIterator[None]:
        # Se cierra la sesión al terminar o ante excepción: los locks se liberan.
        import psycopg

        async with await psycopg.AsyncConnection.connect(self._dsn, connect_timeout=10) as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(%s)", (self._lock_id,))
                yield
