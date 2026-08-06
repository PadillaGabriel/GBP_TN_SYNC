from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.dominio.modelos.imagen import ImagenProducto
from app.dominio.modelos.medidas import MedidasProducto
from app.dominio.modelos.precio import PrecioProducto
from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockDeposito, StockProducto
from app.infraestructura.gbp.cliente import ClienteGBP


class ErrorExportacionGBP(RuntimeError):
    """La exportación GBP no pudo generar un conjunto de datos utilizable."""


@dataclass(slots=True)
class SnapshotExportacionGBP:
    export_id: int
    filas: list[dict[str, str]]
    duracion_ms: int
    generado_en: float


class ProveedorExportacionesGBP:
    """Acceso único a las Exportaciones Personalizadas validadas de GBP."""

    def __init__(self, cliente: ClienteGBP, *, cache_seconds: int = 120) -> None:
        self._cliente = cliente
        self._cache_seconds = max(0, cache_seconds)
        self._cache: dict[int, SnapshotExportacionGBP] = {}

    async def ejecutar(
        self, export_id: int, *, usar_cache: bool = True
    ) -> SnapshotExportacionGBP:
        ahora = time.time()
        cached = self._cache.get(export_id)
        if usar_cache and cached and ahora - cached.generado_en <= self._cache_seconds:
            return cached

        inicio = time.perf_counter()
        filas = await self._cliente.obtener_exportacion(export_id)
        error_generacion = detectar_error_generacion(filas)
        if error_generacion:
            raise ErrorExportacionGBP(
                f"La exportación {export_id} no pudo generarse: {error_generacion}"
            )

        snapshot = SnapshotExportacionGBP(
            export_id=export_id,
            filas=filas,
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            generado_en=ahora,
        )
        self._cache[export_id] = snapshot
        return snapshot

    async def buscar_fila(
        self,
        export_id: int,
        *,
        item_id: str | int | None = None,
        item_code: str | None = None,
        sku: str | None = None,
        usar_cache: bool = True,
    ) -> dict[str, str] | None:
        """Busca por identificador interno o SKU dentro de un snapshot exportado."""

        snapshot = await self.ejecutar(export_id, usar_cache=usar_cache)
        item_id_text = str(item_id).strip() if item_id is not None else ""
        item_code_text = str(item_code or sku or "").strip().casefold()

        for fila in snapshot.filas:
            if item_id_text and str(fila.get("item_id") or "").strip() == item_id_text:
                return fila
            if (
                item_code_text
                and str(fila.get("item_code") or "").strip().casefold()
                == item_code_text
            ):
                return fila
        return None


def detectar_error_generacion(filas: list[dict[str, str]]) -> str | None:
    """Extrae el error funcional que GBP codifica como una fila GenerationError."""

    for fila in filas:
        for clave, valor in fila.items():
            if str(clave).strip().casefold() == "generationerror":
                detalle = str(valor or "").strip()
                return detalle or "GBP devolvió GenerationError sin detalle."
    return None


def producto_desde_exportacion(row: dict[str, str]) -> Producto:
    """Normaliza únicamente la ficha general de la exportación 12."""

    sku = str(row.get("item_code") or "").strip()
    item_id = str(row.get("item_id") or "").strip()
    titulo = str(row.get("descripcion_corta") or row.get("item_desc") or sku).strip()
    descripcion = str(
        row.get("descripcion_larga") or row.get("item_desc") or titulo
    ).strip()
    imagenes = [
        ImagenProducto(url=url.strip(), orden=index)
        for index, url in enumerate(
            str(row.get("imagenes_urls") or "").split("|"), start=1
        )
        if url.strip()
    ]
    activo = _bool(row.get("item_active"), default=True)
    return Producto(
        sku=sku,
        id_sistema_gbp=item_id,
        titulo=titulo,
        codigo_universal=str(row.get("item_codeAlternative") or "").strip() or None,
        codigo_proveedor=str(row.get("item_vendorCode") or "").strip() or None,
        categoria_nombre=str(row.get("category_name") or "").strip() or None,
        subcategoria_nombre=str(row.get("subcategory_name") or "").strip() or None,
        marca_nombre=str(row.get("brand_name") or "").strip() or None,
        publicable_web=_bool(row.get("item_web")),
        item_disabled=_bool(row.get("item_disabled"), default=not activo),
        item_not_for_sale=_bool(row.get("item_not_for_sale"), default=not activo),
        descripcion_web=descripcion,
        medidas=MedidasProducto(
            peso=_decimal(row.get("peso")),
            alto=_decimal(row.get("alto")),
            ancho=_decimal(row.get("ancho")),
            largo=_decimal(row.get("profundidad")),
        ),
        precio_importado=None,
        stock=None,
        imagenes=imagenes,
        payload_crudo=dict(row),
    )


def precio_desde_exportacion(
    row: dict[str, str], *, lista_precio_id: str
) -> PrecioProducto | None:
    """Normaliza el precio final de la exportación 13."""

    monto = _decimal(row.get("precio_final"))
    return PrecioProducto(monto=monto, lista_precio_id=str(lista_precio_id))


def stock_desde_exportacion(
    row: dict[str, str], *, deposito_id: str = "18"
) -> StockProducto:
    """Normaliza stock real de la exportación 14 sin inventar filas ausentes."""

    sku = str(row.get("item_code") or "").strip()
    item_id = str(row.get("item_id") or "").strip()
    active = _bool(row.get("item_active"), default=False) and _bool(
        row.get("item_web"), default=False
    )
    stock_original = _int(row.get("stock_disponible"), default=0)
    cantidad = max(0, stock_original) if active else 0
    return StockProducto(
        sku=sku,
        id_sistema_gbp=item_id,
        cantidad=cantidad,
        stock_original_gbp=float(stock_original),
        depositos=[
            StockDeposito(
                stor_id=str(deposito_id),
                stock_disponible=cantidad,
                stock_original=float(stock_original),
                usado_para_tienda_nube=True,
            )
        ],
    )


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


def _decimal(value: Any) -> Decimal:
    text = str(value or "0").strip().replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(Decimal(str(value or default).replace(",", ".")))
    except (InvalidOperation, ValueError):
        return default
