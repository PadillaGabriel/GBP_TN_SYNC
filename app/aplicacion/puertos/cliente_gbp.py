from __future__ import annotations

from typing import Protocol


class ClienteGBPPuerto(Protocol):
    async def buscar_por_documento(self, documento: str) -> list[dict[str, str]]: ...

    async def resolver_provincia(self, *, country_id: int, provincia: str) -> int: ...

    async def crear_cliente(
        self,
        *,
        nombre: str,
        country_id: int,
        state_id: int,
        direccion: str,
        ciudad: str,
        codigo_postal: str,
        fiscal_class_id: int,
        tax_number_type_id: int,
        documento: str,
        email: str,
        telefono: str,
    ) -> int: ...
