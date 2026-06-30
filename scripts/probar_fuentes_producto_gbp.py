"""Prueba especializada de fuentes GBP por SKU/item_id.

No escribe en GBP ni en Tienda Nube. Sirve para diagnosticar qué fuente devuelve
cada dato operativo de un producto y qué falta sin convertirlo en error fatal.

Ejemplos:
    python scripts/probar_fuentes_producto_gbp.py --sku 536HUELLAS --price-list-id 1 --storage-id 18
    python scripts/probar_fuentes_producto_gbp.py --sku 536HUELLAS --item-id 13170 --price-list-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.errors import GBPProductoNoConsultableError
from app.infrastructure.gbp.client import GBPClient
from app.infrastructure.gbp.normalizer import GBPNormalizer
from app.settings import get_settings


RowsCall = Callable[[], Awaitable[Any]]


def section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def first_value(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    if not row:
        return None

    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()

    lower = {str(k).lower(): v for k, v in row.items()}
    for key in candidates:
        value = lower.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()

    normalized = {
        "".join(ch for ch in str(k).lower() if ch.isalnum()): v
        for k, v in row.items()
    }
    for key in candidates:
        norm_key = "".join(ch for ch in key.lower() if ch.isalnum())
        value = normalized.get(norm_key)
        if value not in (None, ""):
            return str(value).strip()

    return None


def find_by_item_id(rows: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for row in rows:
        row_item_id = first_value(
            row,
            (
                "item_id",
                "Item_ID",
                "ItemID",
                "itemID",
                "intItemID",
                "intItem_id",
                "id",
            ),
        )
        if str(row_item_id or "").strip() == str(item_id).strip():
            return row
    return None


def summarize_rows(rows: Any, *, limit: int = 2) -> None:
    if rows is None:
        print("rows=None")
        return

    if isinstance(rows, dict):
        rows = [rows]

    if not isinstance(rows, list):
        print(repr(rows))
        return

    print(f"rows={len(rows)}")
    if not rows:
        return

    print(f"keys={list(rows[0].keys())}")
    for index, row in enumerate(rows[:limit], start=1):
        print(f"\n--- row {index} ---")
        print(json.dumps(row, ensure_ascii=False, indent=2, default=str)[:3000])


async def safe_call_rows(title: str, call: RowsCall) -> list[dict[str, Any]]:
    section(title)
    try:
        result = await call()
        if isinstance(result, dict):
            rows = [result] if result else []
        elif isinstance(result, list):
            rows = result
        else:
            rows = []
            print(repr(result))
        summarize_rows(rows)
        return rows
    except Exception as exc:  # noqa: BLE001 - diagnóstico no debe cortar por método puntual.
        print(f"NO_FATAL | {type(exc).__name__}: {exc}")
        return []


async def safe_call_method_rows(
    client: GBPClient,
    *,
    token: str,
    title: str,
    method_name: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    from app.infrastructure.gbp.xml_parser import parse_dataset_tables

    section(title)
    try:
        call = await client.call_soap_method(method_name, token=token, params=params)
        rows = parse_dataset_tables(call.result_text)
        print(f"method={method_name}")
        print(f"params={params}")
        print(f"result_len={len(call.result_text or '')}")
        print(f"preview={(call.result_text or '')[:500]}")
        summarize_rows(rows)
        return rows
    except Exception as exc:  # noqa: BLE001 - método alternativo puede no aplicar.
        print(f"NO_FATAL | {method_name} | {type(exc).__name__}: {exc}")
        return []


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", required=True)
    parser.add_argument("--item-id")
    parser.add_argument("--price-list-id", type=int)
    parser.add_argument("--storage-id", type=int, default=None)
    parser.add_argument(
        "--extra-methods",
        action="store_true",
        help="Prueba métodos adicionales de ficha. Algunos pueden devolver error si GBP no los habilita para la instalación.",
    )
    args = parser.parse_args()

    settings = get_settings()
    normalizer = GBPNormalizer()
    client = GBPClient(
        base_url=settings.gbp_base_url,
        username=settings.gbp_username,
        password=settings.gbp_password,
        timeout_seconds=settings.gbp_timeout_seconds,
        company_id=settings.gbp_company_id,
        web_service_id=settings.gbp_web_service_id,
    )

    token = await client.autenticar()
    price_list_id = args.price_list_id or settings.online_price_list_id
    storage_id = args.storage_id if args.storage_id is not None else settings.ecommerce_primary_storage_id

    faltantes: list[str] = []
    advertencias: list[str] = []
    encontrado: dict[str, Any] = {}

    section("CONFIG")
    print(f"SKU={args.sku}")
    print(f"item_id_param={args.item_id}")
    print(f"ONLINE_PRICE_LIST_ID={price_list_id}")
    print(f"ECOMMERCE_STORAGE_IDS={settings.ecommerce_storage_id_list}")
    print(f"storage_id_param={storage_id}")

    item_id = args.item_id
    if not item_id:
        section("IDENTIDAD | wsgetItemIDfromCode_funGetXMLData")
        item_id = await client.obtener_item_id_por_codigo(token, args.sku)
        print(f"item_id={item_id}")

    if not item_id:
        faltantes.append("ITEM_ID")
        section("RESUMEN FINAL")
        print(json.dumps({"sku": args.sku, "faltantes": faltantes, "advertencias": advertencias}, ensure_ascii=False, indent=2))
        return

    encontrado["item_id"] = str(item_id)

    section("FICHA | wsItem_funGetXMLDataById")
    try:
        ficha = await client.obtener_producto_por_id(token, int(item_id))
        encontrado["ficha_wsItem"] = ficha
        summarize_rows([ficha])
    except GBPProductoNoConsultableError as exc:
        advertencias.append("wsItem_funGetXMLDataById_NOT_DATA_FOUND")
        print(f"NO_FATAL | {type(exc).__name__}: {exc}")

    section("FICHA | obtener_producto_por_id_robusto")
    try:
        robusto = await client.obtener_producto_por_id_robusto(token, int(item_id))
        encontrado["ficha_robusta"] = robusto
        summarize_rows([robusto])
    except Exception as exc:  # noqa: BLE001
        advertencias.append("FICHA_ROBUSTA_NO_DISPONIBLE")
        print(f"NO_FATAL | {type(exc).__name__}: {exc}")

    section("FICHA | ItemBasicData_funGetXMLData completo filtrado local")
    try:
        catalogo = await client.obtener_catalogo_basico(token)
        row = find_by_item_id(catalogo, str(item_id))
        print(f"catalogo_rows={len(catalogo)}")
        if row:
            encontrado["ficha_catalogo_basico"] = row
            print("MATCH item_id en catalogo basico completo")
            summarize_rows([row])
        else:
            advertencias.append("ITEM_NO_EN_CATALOGO_BASICO_COMPLETO")
            print("No se encontro item_id en catalogo basico completo")
    except Exception as exc:  # noqa: BLE001
        advertencias.append("CATALOGO_BASICO_ERROR")
        print(f"NO_FATAL | {type(exc).__name__}: {exc}")

    if args.extra_methods:
        await safe_call_method_rows(
            client,
            token=token,
            title="FICHA EXTRA | wsV2_Item_funGetXMLData",
            method_name="wsV2_Item_funGetXMLData",
            params={"intItemID": int(item_id)},
        )
        await safe_call_method_rows(
            client,
            token=token,
            title="FICHA EXTRA | Item_funGetXMLData_Short",
            method_name="Item_funGetXMLData_Short",
            params={"intItem_id": int(item_id)},
        )
        await safe_call_method_rows(
            client,
            token=token,
            title="RELACIONES EXTRA | ws_GetItemAssociationOrComposition",
            method_name="ws_GetItemAssociationOrComposition",
            params={"intItemID": int(item_id)},
        )

    precio_rows = await safe_call_rows(
        f"PRECIO | PriceListItems_funGetXMLData_Short | lista={price_list_id}",
        lambda: client.obtener_precio_por_item_id(token, item_id=int(item_id), price_list_id=price_list_id),
    )
    try:
        precio = normalizer.normalizar_precio(precio_rows, price_list_id=price_list_id)
        if precio:
            encontrado["precio"] = precio.model_dump()
            print("\nPRECIO NORMALIZADO:")
            print(precio.model_dump_json(indent=2))
        else:
            faltantes.append("PRECIO_ONLINE")
            print("\nPRECIO NORMALIZADO: None")
    except Exception as exc:  # noqa: BLE001
        faltantes.append("PRECIO_ONLINE")
        print(f"NO_FATAL | precio normalizer | {type(exc).__name__}: {exc}")

    stock_rows = await safe_call_rows(
        f"STOCK | ItemStorage_funGetXMLData | storage_id={storage_id}",
        lambda: client.obtener_stock_por_item_id(token, item_id=int(item_id), storage_id=storage_id),
    )
    try:
        stock = normalizer.normalizar_stock_desde_filas(
            stock_rows,
            sku=args.sku,
            id_sistema_gbp=str(item_id),
            ecommerce_storage_ids=settings.ecommerce_storage_id_list,
        )
        encontrado["stock"] = stock.model_dump()
        print("\nSTOCK NORMALIZADO:")
        print(stock.model_dump_json(indent=2))
        if stock.cantidad <= 0:
            advertencias.append("STOCK_CERO")
    except Exception as exc:  # noqa: BLE001
        faltantes.append("STOCK_CONSULTABLE")
        print(f"NO_FATAL | stock normalizer | {type(exc).__name__}: {exc}")

    imagenes_rows = await safe_call_rows(
        "IMAGENES | wsGetWebSiteImagesURL4WebServices",
        lambda: client.obtener_imagenes_website_por_item_id(token, int(item_id)),
    )
    try:
        data_imagenes: dict[str, Any] = {}
        for row in imagenes_rows:
            data_imagenes.update(row)
        imagenes = normalizer._normalizar_imagenes(data_imagenes)
        if imagenes:
            encontrado["imagenes"] = [img.model_dump() for img in imagenes]
            print("\nIMAGENES NORMALIZADAS:")
            print(json.dumps(encontrado["imagenes"], ensure_ascii=False, indent=2))
        else:
            faltantes.append("IMAGENES_WEBSITE")
            print("\nIMAGENES NORMALIZADAS: []")
    except Exception as exc:  # noqa: BLE001
        faltantes.append("IMAGENES_WEBSITE")
        print(f"NO_FATAL | imagenes normalizer | {type(exc).__name__}: {exc}")

    section("PRODUCTO NORMALIZADO")
    ficha_final = (
        encontrado.get("ficha_wsItem")
        or encontrado.get("ficha_robusta")
        or encontrado.get("ficha_catalogo_basico")
    )
    if ficha_final:
        try:
            producto_data = dict(ficha_final)
            precio_dump = encontrado.get("precio") or {}
            if precio_dump.get("monto") is not None:
                producto_data["precio_online"] = precio_dump["monto"]
                producto_data["prli_id"] = precio_dump.get("lista_precio_id") or str(price_list_id)
            data_imagenes = {}
            for imagen in encontrado.get("imagenes", []):
                data_imagenes[f"item_WebSite_url4Image{imagen.get('orden', 1)}"] = imagen.get("url")
            producto_data.update(data_imagenes)
            producto = normalizer.normalizar_producto(producto_data)
            print(producto.model_dump_json(indent=2))
        except Exception as exc:  # noqa: BLE001
            advertencias.append("PRODUCTO_COMPLETO_NO_NORMALIZABLE")
            print(f"NO_FATAL | producto normalizer | {type(exc).__name__}: {exc}")
    else:
        faltantes.append("FICHA_PRODUCTO")
        print("No hay ficha suficiente para normalizar producto completo.")

    section("RESUMEN FINAL")
    recomendacion = "REQUIERE_REVISION"
    if item_id and ("precio" in encontrado or "imagenes" in encontrado or "stock" in encontrado):
        recomendacion = "PUBLICABLE_CON_DATOS_PARCIALES_MANUAL"
    if item_id and "precio" in encontrado and "imagenes" in encontrado:
        recomendacion = "PUBLICABLE_MANUAL_CON_PRECIO_E_IMAGENES"
    if item_id and "precio" in encontrado and "stock" in encontrado and "imagenes" in encontrado:
        recomendacion = "PUBLICABLE_MANUAL_CON_PRECIO_STOCK_E_IMAGENES"

    print(json.dumps(
        {
            "sku": args.sku,
            "item_id": str(item_id),
            "encontrado": sorted(encontrado.keys()),
            "faltantes": faltantes,
            "advertencias": advertencias,
            "recomendacion": recomendacion,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    ))


if __name__ == "__main__":
    asyncio.run(main())
