"""Audita masivamente el campo item_web en GBP.

Objetivo:
    Determinar si item_web sirve como criterio real para decidir qué productos
    deben importarse/publicarse en Tienda Nube.

Este script solo usa métodos de lectura. No escribe en GBP ni en Tienda Nube.

Uso recomendado inicial:
    python scripts/auditar_item_web.py --source basic

Si el catálogo básico no trae item_web o se quiere validar con ficha completa:
    python scripts/auditar_item_web.py --source detail --limit 200 --concurrency 5

Auditoría completa por detalle, más pesada:
    python scripts/auditar_item_web.py --source detail --concurrency 5
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx

SOAP_NAMESPACE = "http://microsoft.com/webservices/"
SOAP_ACTION_PREFIX = SOAP_NAMESPACE.rstrip("/")
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
DEFAULT_BASE_URL = (
    "http://ws.globalbluepoint.com/silmarbazar/app_webservices/wsBasicQuery.asmx"
)
OUTPUT_DIR = Path("diagnostics/gbp/item_web")


@dataclass(frozen=True)
class GBPConfig:
    """Configuración del Web Service GBP."""

    base_url: str
    username: str
    password: str
    company: int
    web_service: int
    timeout_seconds: float


@dataclass(frozen=True)
class ProductAuditRow:
    """Fila normalizada de auditoría de publicabilidad."""

    item_id: str
    item_code: str
    item_desc: str
    item_web: str
    item_disabled: str
    item_not4_sale: str
    image_existing: str
    has_website_image: bool
    has_website_description: bool
    cat_desc: str
    subcat_desc: str
    brand_desc: str
    decision: str
    source: str
    duration_ms: int | None = None
    error: str | None = None


def load_env_file(path: Path = Path(".env")) -> None:
    """Carga variables simples desde .env sin pisar variables existentes."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_required_env(name: str) -> str:
    """Obtiene una variable obligatoria."""

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta configurar {name} en .env")
    return value


def load_config() -> GBPConfig:
    """Construye configuración desde .env / entorno."""

    load_env_file()
    return GBPConfig(
        base_url=os.getenv("GBP_BASE_URL", DEFAULT_BASE_URL).strip(),
        username=get_required_env("GBP_USERNAME"),
        password=get_required_env("GBP_PASSWORD"),
        company=int(get_required_env("GBP_COMPANY_ID")),
        web_service=int(get_required_env("GBP_WEB_SERVICE_ID")),
        timeout_seconds=float(os.getenv("GBP_TIMEOUT_SECONDS", "60")),
    )


def safe_xml_value(value: Any) -> str:
    """Convierte un valor a texto XML seguro."""

    if isinstance(value, bool):
        return "true" if value else "false"
    return escape(str(value))


def build_soap_envelope(
    *,
    config: GBPConfig,
    token: str,
    method_name: str,
    params: dict[str, Any],
) -> str:
    """Arma un envelope SOAP 1.1 compatible con GBP."""

    body_params = "".join(
        f"<{name}>{safe_xml_value(value)}</{name}>" for name, value in params.items()
    )
    return f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="{SOAP_ENV}">
  <soap:Header>
    <wsBasicQueryHeader xmlns="{SOAP_NAMESPACE}">
      <pUsername>{safe_xml_value(config.username)}</pUsername>
      <pPassword>{safe_xml_value(config.password)}</pPassword>
      <pCompany>{config.company}</pCompany>
      <pWebWervice>{config.web_service}</pWebWervice>
      <pAuthenticatedToken>{safe_xml_value(token)}</pAuthenticatedToken>
    </wsBasicQueryHeader>
  </soap:Header>
  <soap:Body>
    <{method_name} xmlns="{SOAP_NAMESPACE}">{body_params}</{method_name}>
  </soap:Body>
</soap:Envelope>'''


def strip_namespace(tag: str) -> str:
    """Elimina namespace de un tag XML."""

    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_xml_text(text: str) -> str:
    """Limpia XML interno devuelto por GBP antes de parsearlo.

    GBP puede devolver el XML interno como texto escapado dentro del SOAP o como
    XML ya desescapado. Si se aplica html.unescape sin control sobre un XML ya
    desescapado, los valores que contienen &amp; pasan a tener & crudo y rompen
    el parser. Por eso solo desescapamos cuando el documento parece venir como
    entidades XML.
    """

    cleaned = (text or "").strip().lstrip("\ufeff")

    if cleaned.startswith("&lt;") or "&lt;NewDataSet" in cleaned[:200]:
        cleaned = html.unescape(cleaned)

    # XML 1.0 permite tab, LF, CR y caracteres desde espacio en adelante.
    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", cleaned)

    # GBP puede traer ampersands crudos dentro de descripciones. Escapar solo
    # los que no forman parte de una entidad XML válida.
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        cleaned,
    )
    return cleaned


def write_parse_error_context(cleaned: str, exc: ET.ParseError) -> Path:
    """Guarda contexto local del XML que no pudo parsearse."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"xml_parse_error_context_{stamp}.txt"

    position = getattr(exc, "position", None)
    lines = cleaned.splitlines()
    context_lines: list[str] = []

    if position:
        line_number, column = position
        start = max(1, line_number - 5)
        end = min(len(lines), line_number + 5)
        context_lines.append(f"ParseError: {exc}")
        context_lines.append(f"line={line_number} column={column}")
        context_lines.append("")
        for index in range(start, end + 1):
            prefix = ">>> " if index == line_number else "    "
            context_lines.append(f"{prefix}{index}: {lines[index - 1]}")
    else:
        context_lines.append(f"ParseError: {exc}")
        context_lines.append(cleaned[:5000])

    path.write_text("\n".join(context_lines), encoding="utf-8", errors="replace")
    return path


def extract_result_text(soap_text: str, method_name: str) -> str:
    """Extrae el contenido del nodo *Result de una respuesta SOAP."""

    root = ET.fromstring(soap_text)
    expected = f"{method_name}Result"
    for node in root.iter():
        if strip_namespace(node.tag) == expected:
            return node.text or ""
    for node in root.iter():
        if strip_namespace(node.tag).endswith("Result"):
            return node.text or ""
    return ""


async def call_method(
    *,
    client: httpx.AsyncClient,
    config: GBPConfig,
    token: str,
    method_name: str,
    params: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Ejecuta un método SOAP y devuelve resultado interno + duración."""

    started = time.perf_counter()
    envelope = build_soap_envelope(
        config=config,
        token=token,
        method_name=method_name,
        params=params or {},
    )
    response = await client.post(
        config.base_url,
        content=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{SOAP_ACTION_PREFIX}/{method_name}"',
        },
    )
    response.raise_for_status()
    duration_ms = int((time.perf_counter() - started) * 1000)
    return extract_result_text(response.text, method_name), duration_ms


async def authenticate(client: httpx.AsyncClient, config: GBPConfig) -> str:
    """Autentica y devuelve token."""

    result_text, _duration_ms = await call_method(
        client=client,
        config=config,
        token="",
        method_name="AuthenticateUser",
    )
    token = (result_text or "").strip()
    lower = token.lower()
    if not token or "invalid username" in lower or "password" in lower:
        raise RuntimeError(f"Falló AuthenticateUser: {token}")
    return token


def parse_dataset_tables(result_text: str) -> list[dict[str, str]]:
    """Convierte un NewDataSet XML en lista de dicts por Table."""

    cleaned = clean_xml_text(result_text)
    if not cleaned or cleaned.lower() == "not data found.":
        return []

    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        context_path = write_parse_error_context(cleaned, exc)
        raise RuntimeError(
            "No se pudo parsear XML interno luego de sanitizar. "
            f"Contexto guardado en: {context_path}. Error: {exc}"
        ) from exc

    rows: list[dict[str, str]] = []
    for table in root.iter():
        if strip_namespace(table.tag) != "Table":
            continue
        row: dict[str, str] = {}
        for child in list(table):
            row[strip_namespace(child.tag)] = (child.text or "").strip()
        rows.append(row)
    return rows


def to_bool_text(value: str) -> str:
    """Normaliza booleanos textuales conservando estado desconocido."""

    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "si", "sí"}:
        return "true"
    if normalized in {"false", "0", "no"}:
        return "false"
    return ""


def has_value(value: str) -> bool:
    """Indica si un campo tiene contenido real."""

    return bool((value or "").strip())


def any_website_image(row: dict[str, str]) -> bool:
    """Detecta si hay al menos una imagen Website cargada."""

    for index in range(1, 11):
        if has_value(row.get(f"item_WebSite_url4Image{index}", "")):
            return True
    return False


def decide_publicability(row: dict[str, str], source: str) -> str:
    """Sugiere decisión explicable sin modificar datos."""

    item_web = to_bool_text(row.get("item_web", ""))
    item_disabled = to_bool_text(row.get("item_disabled", ""))
    item_not4_sale = to_bool_text(row.get("item_not4Sale", ""))

    if item_disabled == "true":
        return "NO_PUBLICABLE_ITEM_DISABLED"
    if item_not4_sale == "true":
        return "NO_PUBLICABLE_ITEM_NOT4SALE"
    if item_web == "true":
        return "PUBLICABLE_ITEM_WEB_TRUE"
    if item_web == "false":
        return "NO_PUBLICABLE_ITEM_WEB_FALSE"

    if any_website_image(row):
        return "CANDIDATO_POR_IMAGEN_WEB_SIN_ITEM_WEB"

    if source == "basic" and "item_web" not in row:
        return "NO_DECIDIBLE_BASIC_SIN_ITEM_WEB"

    return "NO_PUBLICABLE_SIN_SENAL_WEB"


def row_from_product_data(row: dict[str, str], source: str, duration_ms: int | None = None) -> ProductAuditRow:
    """Normaliza una fila GBP a ProductAuditRow."""

    website_description = row.get("WebSite_Description", "")
    website_short = row.get("WebSite_ShortDescription", "")
    website_copete = row.get("WebSite_Copete", "")

    return ProductAuditRow(
        item_id=row.get("item_id", ""),
        item_code=row.get("item_code", ""),
        item_desc=row.get("item_desc", ""),
        item_web=to_bool_text(row.get("item_web", "")),
        item_disabled=to_bool_text(row.get("item_disabled", "")),
        item_not4_sale=to_bool_text(row.get("item_not4Sale", "")),
        image_existing=row.get("imageExisting", ""),
        has_website_image=any_website_image(row),
        has_website_description=any(
            has_value(value) for value in [website_description, website_short, website_copete]
        ),
        cat_desc=row.get("cat_desc", ""),
        subcat_desc=row.get("subcat_desc", ""),
        brand_desc=row.get("brand_desc", ""),
        decision=decide_publicability(row, source),
        source=source,
        duration_ms=duration_ms,
    )


async def audit_from_basic_catalog(
    client: httpx.AsyncClient,
    config: GBPConfig,
    token: str,
) -> tuple[list[ProductAuditRow], dict[str, Any]]:
    """Audita usando catálogo básico completo."""

    result_text, duration_ms = await call_method(
        client=client,
        config=config,
        token=token,
        method_name="ItemBasicData_funGetXMLData",
        params={"bitOnlyNewOrUpdated": False},
    )
    rows = parse_dataset_tables(result_text)
    audited = [row_from_product_data(row, "basic") for row in rows]
    fields = sorted({field for row in rows for field in row})
    meta = {
        "source": "basic",
        "duration_ms": duration_ms,
        "raw_rows": len(rows),
        "fields": fields,
        "has_item_web_field": "item_web" in fields,
    }
    return audited, meta


async def audit_detail_for_item(
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    config: GBPConfig,
    token: str,
    item_id: str,
) -> ProductAuditRow:
    """Audita un producto por ficha completa."""

    async with semaphore:
        try:
            result_text, duration_ms = await call_method(
                client=client,
                config=config,
                token=token,
                method_name="wsItem_funGetXMLDataById",
                params={"intItemID": int(item_id)},
            )
            rows = parse_dataset_tables(result_text)
            if not rows:
                return ProductAuditRow(
                    item_id=str(item_id),
                    item_code="",
                    item_desc="",
                    item_web="",
                    item_disabled="",
                    item_not4_sale="",
                    image_existing="",
                    has_website_image=False,
                    has_website_description=False,
                    cat_desc="",
                    subcat_desc="",
                    brand_desc="",
                    decision="ERROR_SIN_DATOS",
                    source="detail",
                    duration_ms=duration_ms,
                    error="Sin datos",
                )
            return row_from_product_data(rows[0], "detail", duration_ms=duration_ms)
        except Exception as exc:  # noqa: BLE001 - se registra para auditoría.
            return ProductAuditRow(
                item_id=str(item_id),
                item_code="",
                item_desc="",
                item_web="",
                item_disabled="",
                item_not4_sale="",
                image_existing="",
                has_website_image=False,
                has_website_description=False,
                cat_desc="",
                subcat_desc="",
                brand_desc="",
                decision="ERROR_CONSULTA_DETALLE",
                source="detail",
                error=f"{type(exc).__name__}: {exc}",
            )


async def audit_from_detail(
    client: httpx.AsyncClient,
    config: GBPConfig,
    token: str,
    item_ids: list[str],
    concurrency: int,
) -> tuple[list[ProductAuditRow], dict[str, Any]]:
    """Audita por ficha completa con concurrencia controlada."""

    started = time.perf_counter()
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        audit_detail_for_item(semaphore, client, config, token, item_id)
        for item_id in item_ids
    ]
    rows = await asyncio.gather(*tasks)
    duration_ms = int((time.perf_counter() - started) * 1000)
    meta = {
        "source": "detail",
        "duration_ms": duration_ms,
        "raw_rows": len(rows),
        "concurrency": concurrency,
    }
    return rows, meta


def load_item_ids_from_csv(path: Path) -> list[str]:
    """Carga item_id desde CSV. Acepta columnas item_id o id_sistema_gbp."""

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        item_ids: list[str] = []
        for row in reader:
            value = (row.get("item_id") or row.get("id_sistema_gbp") or "").strip()
            if value:
                item_ids.append(value)
    return item_ids


def summarize(rows: list[ProductAuditRow], meta: dict[str, Any]) -> dict[str, Any]:
    """Calcula resumen de auditoría."""

    total = len(rows)
    item_web_true = sum(1 for row in rows if row.item_web == "true")
    item_web_false = sum(1 for row in rows if row.item_web == "false")
    item_web_empty = sum(1 for row in rows if not row.item_web)
    disabled_true = sum(1 for row in rows if row.item_disabled == "true")
    not4_sale_true = sum(1 for row in rows if row.item_not4_sale == "true")
    with_image = sum(1 for row in rows if row.has_website_image)
    with_web_desc = sum(1 for row in rows if row.has_website_description)
    errors = sum(1 for row in rows if row.error)

    by_decision: dict[str, int] = {}
    for row in rows:
        by_decision[row.decision] = by_decision.get(row.decision, 0) + 1

    def pct(value: int) -> float:
        return round((value / total) * 100, 2) if total else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "total": total,
        "item_web_true": item_web_true,
        "item_web_true_pct": pct(item_web_true),
        "item_web_false": item_web_false,
        "item_web_false_pct": pct(item_web_false),
        "item_web_empty": item_web_empty,
        "item_web_empty_pct": pct(item_web_empty),
        "item_disabled_true": disabled_true,
        "item_not4_sale_true": not4_sale_true,
        "with_website_image": with_image,
        "with_website_image_pct": pct(with_image),
        "with_website_description": with_web_desc,
        "with_website_description_pct": pct(with_web_desc),
        "errors": errors,
        "by_decision": by_decision,
    }


def write_outputs(rows: list[ProductAuditRow], summary: dict[str, Any]) -> tuple[Path, Path]:
    """Escribe CSV detallado y JSON resumen."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"item_web_audit_{stamp}.csv"
    json_path = OUTPUT_DIR / f"item_web_audit_summary_{stamp}.json"

    fieldnames = list(ProductAuditRow.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def print_summary(summary: dict[str, Any], csv_path: Path, json_path: Path) -> None:
    """Imprime resumen legible."""

    print("\nAuditoría item_web GBP")
    print("=" * 80)
    print(f"Total productos auditados: {summary['total']}")
    print(
        f"item_web=true:  {summary['item_web_true']} "
        f"({summary['item_web_true_pct']}%)"
    )
    print(
        f"item_web=false: {summary['item_web_false']} "
        f"({summary['item_web_false_pct']}%)"
    )
    print(
        f"item_web vacío: {summary['item_web_empty']} "
        f"({summary['item_web_empty_pct']}%)"
    )
    print(f"item_disabled=true: {summary['item_disabled_true']}")
    print(f"item_not4Sale=true: {summary['item_not4_sale_true']}")
    print(
        f"Con imagen Website: {summary['with_website_image']} "
        f"({summary['with_website_image_pct']}%)"
    )
    print(
        f"Con descripción Website: {summary['with_website_description']} "
        f"({summary['with_website_description_pct']}%)"
    )
    print(f"Errores: {summary['errors']}")
    print("\nDecisiones:")
    for decision, count in sorted(summary["by_decision"].items()):
        print(f"  {decision}: {count}")
    print(f"\nCSV:  {csv_path}")
    print(f"JSON: {json_path}")


def parse_args() -> argparse.Namespace:
    """Parsea argumentos CLI."""

    parser = argparse.ArgumentParser(description="Audita item_web para productos GBP.")
    parser.add_argument(
        "--source",
        choices=["basic", "detail"],
        default="basic",
        help="basic usa ItemBasicData completo. detail usa wsItem por producto.",
    )
    parser.add_argument(
        "--item-ids-csv",
        type=Path,
        help="CSV con columna item_id o id_sistema_gbp para auditoría detail.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limita cantidad de productos a auditar.",
    )
    parser.add_argument(
        "--only-with-basic-image",
        action="store_true",
        help=(
            "Con source=detail, primero consulta el catálogo básico y audita "
            "solo productos con al menos una imagen Website."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrencia para source=detail. Default: 5.",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Punto de entrada asincrónico."""

    args = parse_args()
    config = load_config()

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        token = await authenticate(client, config)

        if args.source == "basic":
            rows, meta = await audit_from_basic_catalog(client, config, token)
        else:
            if args.item_ids_csv:
                item_ids = load_item_ids_from_csv(args.item_ids_csv)
            else:
                basic_rows, basic_meta = await audit_from_basic_catalog(client, config, token)
                if args.only_with_basic_image:
                    item_ids = [
                        row.item_id
                        for row in basic_rows
                        if row.item_id and row.has_website_image
                    ]
                else:
                    item_ids = [row.item_id for row in basic_rows if row.item_id]
                meta = {
                    "basic_catalog_for_ids": basic_meta,
                    "only_with_basic_image": args.only_with_basic_image,
                    "candidate_item_ids_before_limit": len(item_ids),
                }
            if args.limit:
                item_ids = item_ids[: args.limit]
            rows, detail_meta = await audit_from_detail(
                client=client,
                config=config,
                token=token,
                item_ids=item_ids,
                concurrency=args.concurrency,
            )
            if "meta" not in locals():
                meta = {}
            meta.update(detail_meta)

    summary = summarize(rows, meta)
    csv_path, json_path = write_outputs(rows, summary)
    print_summary(summary, csv_path, json_path)


def main() -> None:
    """Punto de entrada CLI."""

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
