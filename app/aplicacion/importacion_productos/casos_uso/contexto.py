from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ContextoImportacionProductos:
    settings: Any
    db: Any
    gbp_client: Any
    normalizer: Any
    validation_service: Any
    productos_repo: Any
    audit_repo: Any
    payload_builder: Any
    resolvedor_producto: Any
    persistidor_producto: Any
    fabrica_tienda_nube: Any
