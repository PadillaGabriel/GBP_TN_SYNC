from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.infraestructura.gbp.analizador_xml import parse_dataset_tables


def _decimal_o_none(valor: object) -> Decimal | None:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def analizar_expansion_temporal_gbp(
    xml: str,
    items_insertados: list[dict[str, object]],
) -> dict[str, object]:
    """Compara las líneas enviadas con el detalle materializado por GBP.

    GBP puede reemplazar un artículo padre asociado por sus componentes. Este
    análisis no intenta recrear la relación internamente: registra de forma
    determinista qué padres permanecieron, cuáles fueron expandidos y qué líneas
    fueron generadas por GBP.
    """

    filas = parse_dataset_tables(xml)
    ids_enviados = {int(item["item_id"]) for item in items_insertados}
    ids_devueltos: set[int] = set()
    detalle: list[dict[str, object]] = []

    for fila in filas:
        item_id_bruto = fila.get("item_id")
        try:
            item_id = int(str(item_id_bruto))
        except (TypeError, ValueError):
            continue
        ids_devueltos.add(item_id)
        cantidad = _decimal_o_none(fila.get("tis_qty"))
        precio = _decimal_o_none(fila.get("tis_price"))
        detalle.append(
            {
                "item_id": item_id,
                "sku": str(fila.get("item_code") or "").strip(),
                "descripcion": str(fila.get("item_desc") or "").strip(),
                "cantidad": str(cantidad) if cantidad is not None else None,
                "precio_neto": str(precio) if precio is not None else None,
                "deposito_id": fila.get("stor_id"),
                "origen": "ITEM_ENVIADO"
                if item_id in ids_enviados
                else "GENERADO_POR_GBP",
            }
        )

    padres_expandidos = sorted(ids_enviados - ids_devueltos)
    items_conservados = sorted(ids_enviados & ids_devueltos)
    componentes_generados = sorted(ids_devueltos - ids_enviados)

    return {
        "expansion_detectada": bool(padres_expandidos or componentes_generados),
        "items_enviados": sorted(ids_enviados),
        "items_conservados": items_conservados,
        "padres_expandidos": padres_expandidos,
        "componentes_generados": componentes_generados,
        "cantidad_lineas_enviadas": len(items_insertados),
        "cantidad_lineas_materializadas": len(detalle),
        "detalle_materializado": detalle,
        "regla": "GBP_ES_AUTORIDAD_DE_EXPANSION; EL_INTEGRADOR_INSERTA_SOLO_EL_PADRE",
    }
