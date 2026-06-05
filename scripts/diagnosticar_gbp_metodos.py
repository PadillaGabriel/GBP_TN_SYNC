"""Diagnóstico temporal de métodos GBP Módulo 16.

Este script no escribe en GBP ni en Tienda Nube. Solo consulta métodos de lectura,
mide tiempos, parsea respuestas y deja evidencia para decidir qué conviene usar en
cada flujo del integrador GBP -> Tienda Nube.

Uso típico:
    python scripts/diagnosticar_gbp_metodos.py --sku ABC123 --item-id 123

Uso seguro inicial:
    python scripts/diagnosticar_gbp_metodos.py --only-auth

Uso con respuestas crudas:
    python scripts/diagnosticar_gbp_metodos.py --sku ABC123 --item-id 123 --save-raw
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import time
from dataclasses import dataclass, field
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
OUTPUT_DIR = Path("diagnostics/gbp")


@dataclass(frozen=True)
class MethodSpec:
    """Definición mínima de un método de diagnóstico."""

    name: str
    purpose: str
    declared_module: str
    recommended_use: str
    params: dict[str, Any] = field(default_factory=dict)
    heavy: bool = False
    requires_item_id: bool = False
    requires_sku: bool = False
    requires_price_list: bool = False


@dataclass
class GBPConfig:
    """Configuración necesaria para consultar GBP."""

    base_url: str
    username: str
    password: str
    company: int
    web_service: int
    timeout_seconds: float


@dataclass
class DiagnosticResult:
    """Resultado normalizado de una consulta diagnóstica."""

    executed_at: str
    method: str
    purpose: str
    declared_module: str
    recommended_use: str
    params: dict[str, Any]
    http_status: int | None
    ok: bool
    duration_ms: int
    soap_bytes: int
    result_bytes: int
    xml_node_count: int
    detected_fields: list[str]
    preview: str
    error: str | None
    raw_file: str | None


def load_env_file(path: Path = Path(".env")) -> None:
    """Carga variables simples desde .env sin pisar variables ya existentes."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_required_env(name: str) -> str:
    """Obtiene una variable de entorno obligatoria."""

    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta configurar la variable {name} en .env")
    return value


def load_config() -> GBPConfig:
    """Construye configuración desde variables de entorno."""

    load_env_file()
    return GBPConfig(
        base_url=os.getenv("GBP_BASE_URL", DEFAULT_BASE_URL).strip(),
        username=get_required_env("GBP_USERNAME"),
        password=get_required_env("GBP_PASSWORD"),
        company=int(get_required_env("GBP_COMPANY_ID")),
        web_service=int(get_required_env("GBP_WEB_SERVICE_ID")),
        timeout_seconds=float(os.getenv("GBP_TIMEOUT_SECONDS", "30")),
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
    """Arma un envelope SOAP 1.1 para GBP."""

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


def parse_inner_xml(result_text: str) -> tuple[int, list[str]]:
    """Intenta parsear el resultado interno como XML y extrae nodos/campos."""

    decoded = html.unescape(result_text or "").strip()
    if not decoded:
        return 0, []

    try:
        root = ET.fromstring(decoded)
    except ET.ParseError:
        return 0, []

    fields: set[str] = set()
    count = 0
    for node in root.iter():
        count += 1
        tag = strip_namespace(node.tag)
        if tag:
            fields.add(tag)
    return count, sorted(fields)[:80]


def make_preview(result_text: str, limit: int = 500) -> str:
    """Genera preview corto y seguro para consola/log."""

    text = html.unescape(result_text or "").replace("\r", " ").replace("\n", " ")
    normalized = " ".join(text.split())
    return normalized[:limit]


def save_raw_response(method_name: str, soap_text: str) -> str:
    """Guarda respuesta cruda SOAP para inspección manual."""

    raw_dir = OUTPUT_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    path = raw_dir / f"{stamp}_{method_name}.xml"
    path.write_text(soap_text, encoding="utf-8")
    return str(path)


def call_method(
    *,
    client: httpx.Client,
    config: GBPConfig,
    token: str,
    spec: MethodSpec,
    save_raw: bool,
) -> DiagnosticResult:
    """Ejecuta un método y devuelve resultado de diagnóstico."""

    started = time.perf_counter()
    status_code: int | None = None
    soap_text = ""
    result_text = ""
    raw_file: str | None = None
    error: str | None = None
    ok = False

    try:
        envelope = build_soap_envelope(
            config=config,
            token=token,
            method_name=spec.name,
            params=spec.params,
        )
        response = client.post(
            config.base_url,
            content=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{SOAP_ACTION_PREFIX}/{spec.name}"',
            },
        )
        status_code = response.status_code
        soap_text = response.text
        response.raise_for_status()
        result_text = extract_result_text(soap_text, spec.name)
        ok = bool(result_text) or spec.name == "AuthenticateUser"
        if save_raw:
            raw_file = save_raw_response(spec.name, soap_text)
    except Exception as exc:  # noqa: BLE001 - diagnóstico temporal, se registra completo.
        error = f"{type(exc).__name__}: {exc}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    node_count, detected_fields = parse_inner_xml(result_text)

    return DiagnosticResult(
        executed_at=datetime.now(timezone.utc).isoformat(),
        method=spec.name,
        purpose=spec.purpose,
        declared_module=spec.declared_module,
        recommended_use=spec.recommended_use,
        params=spec.params,
        http_status=status_code,
        ok=ok and error is None,
        duration_ms=duration_ms,
        soap_bytes=len(soap_text.encode("utf-8")) if soap_text else 0,
        result_bytes=len((result_text or "").encode("utf-8")),
        xml_node_count=node_count,
        detected_fields=detected_fields,
        preview=make_preview(result_text),
        error=error,
        raw_file=raw_file,
    )


def authenticate(client: httpx.Client, config: GBPConfig, save_raw: bool) -> tuple[str, DiagnosticResult]:
    """Autentica contra GBP y devuelve token más resultado."""

    spec = MethodSpec(
        name="AuthenticateUser",
        purpose="Autenticación y validación del Web Service",
        declared_module="Módulo 16 operativo",
        recommended_use="Obligatorio antes de consultar métodos",
    )
    result = call_method(
        client=client,
        config=config,
        token="",
        spec=spec,
        save_raw=save_raw,
    )
    token = result.preview.strip()
    if not result.ok or not token:
        raise RuntimeError(f"Falló AuthenticateUser: {result.error or result.preview}")
    return token, result


def build_method_specs(args: argparse.Namespace) -> list[MethodSpec]:
    """Construye la lista de métodos a diagnosticar según argumentos."""

    item_id = args.item_id
    sku = args.sku
    storage_id = args.storage_id
    price_list_id = args.price_list_id

    specs = [
        MethodSpec(
            name="Brand_funGetXMLData",
            purpose="Cache auxiliar de marcas",
            declared_module="Módulo 16",
            recommended_use="Cache diario/manual",
        ),
        MethodSpec(
            name="Category_funGetXMLData",
            purpose="Cache auxiliar de categorías",
            declared_module="Módulo 16",
            recommended_use="Cache diario/manual",
        ),
        MethodSpec(
            name="SubCategory_funGetXMLData",
            purpose="Cache auxiliar de subcategorías",
            declared_module="Módulo 16",
            recommended_use="Cache diario/manual",
        ),
        MethodSpec(
            name="MeasurementUnits_funGetXMLData",
            purpose="Cache auxiliar de unidades de medida",
            declared_module="Módulo 16",
            recommended_use="Cache diario/manual",
        ),
        MethodSpec(
            name="PriceList_funGetXMLData",
            purpose="Identificar listas de precio disponibles",
            declared_module="Módulo 16",
            recommended_use="Cache manual/diario; prerrequisito de importación",
        ),
        MethodSpec(
            name="ItemBasicData_funGetXMLData",
            purpose="Artículos básicos actualizados",
            declared_module="Módulo 16",
            recommended_use="Descubrimiento incremental",
            params={"bitOnlyNewOrUpdated": True},
        ),
    ]

    if args.include_full_catalog:
        specs.extend(
            [
                MethodSpec(
                    name="ItemBasicData_funGetXMLData",
                    purpose="Artículos básicos completos",
                    declared_module="Módulo 16",
                    recommended_use="Benchmark para carga inicial completa",
                    params={"bitOnlyNewOrUpdated": False},
                    heavy=True,
                ),
                MethodSpec(
                    name="Item_funGetXMLData_Short",
                    purpose="Lista corta completa de artículos",
                    declared_module="Módulo 16",
                    recommended_use="Benchmark para carga inicial completa",
                    heavy=True,
                ),
            ]
        )

    if sku:
        specs.append(
            MethodSpec(
                name="wsgetItemIDfromCode_funGetXMLData",
                purpose="Resolver SKU/código a ID interno GBP",
                declared_module="Módulo 16",
                recommended_use="Bajo demanda y diagnóstico de mapeo",
                params={"strItemCode": sku},
                requires_sku=True,
            )
        )

    if item_id is not None:
        specs.extend(
            [
                MethodSpec(
                    name="wsItem_funGetXMLDataById",
                    purpose="Ficha completa de artículo por ID GBP",
                    declared_module="Módulo 16",
                    recommended_use="Importación inicial y actualización completa manual",
                    params={"intItemID": item_id},
                    requires_item_id=True,
                ),
                MethodSpec(
                    name="ItemStorage_funGetXMLData",
                    purpose="Stock por artículo y depósito",
                    declared_module="Módulo 16",
                    recommended_use="Candidato principal para sync frecuente de stock",
                    params={"intStor_id": storage_id, "intItem_id": item_id},
                    requires_item_id=True,
                ),
                MethodSpec(
                    name="ItemImages_funGetXMLData",
                    purpose="Imágenes por artículo",
                    declared_module="Módulo 16",
                    recommended_use="Importación inicial y actualización completa manual",
                    params={"intItemId": item_id},
                    requires_item_id=True,
                ),
                MethodSpec(
                    name="wsGetWebSiteImagesURL4WebServices",
                    purpose="URLs de imágenes Website IV para artículo",
                    declared_module="Módulos 16 / 45 / 78; usando rama Módulo 16",
                    recommended_use="Candidato preferido para imágenes de Tienda Nube",
                    params={
                        "intItemID": item_id,
                        "bolIsAvailable4Web": True,
                        "bolIsAvailable4FulljausAndProducteca": False,
                    },
                    requires_item_id=True,
                ),
            ]
        )

    if price_list_id is not None and item_id is not None:
        specs.append(
            MethodSpec(
                name="PriceListItems_funGetXMLData_Short",
                purpose="Precio inicial por lista y artículo",
                declared_module="Módulo 16",
                recommended_use="Importación inicial; no frecuente",
                params={"pPriceList": price_list_id, "pItem": item_id},
                requires_price_list=True,
                requires_item_id=True,
            )
        )

    if args.include_heavy_stock:
        specs.append(
            MethodSpec(
                name="ItemStorage_funGetXMLData",
                purpose="Benchmark pesado de stock completo",
                declared_module="Módulo 16",
                recommended_use="Solo diagnóstico; no scheduler frecuente",
                params={"intStor_id": -1, "intItem_id": -1},
                heavy=True,
            )
        )

    if args.method:
        wanted = set(args.method)
        specs = [spec for spec in specs if spec.name in wanted]

    return specs


def write_jsonl(results: list[DiagnosticResult]) -> Path:
    """Escribe resultados en JSONL."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "gbp_diagnostic_results.jsonl"
    with path.open("a", encoding="utf-8") as file:
        for result in results:
            file.write(json.dumps(result.__dict__, ensure_ascii=False, default=str) + "\n")
    return path


def write_summary_csv(results: list[DiagnosticResult]) -> Path:
    """Escribe resumen CSV sobrescribible de la última corrida."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "gbp_diagnostic_summary.csv"
    fieldnames = [
        "executed_at",
        "method",
        "purpose",
        "declared_module",
        "recommended_use",
        "http_status",
        "ok",
        "duration_ms",
        "soap_bytes",
        "result_bytes",
        "xml_node_count",
        "detected_fields",
        "error",
        "raw_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = result.__dict__.copy()
            row["detected_fields"] = ",".join(result.detected_fields)
            writer.writerow({key: row.get(key) for key in fieldnames})
    return path


def print_summary(results: list[DiagnosticResult]) -> None:
    """Imprime resumen compacto por consola."""

    print("\nResumen diagnóstico GBP")
    print("=" * 80)
    for result in results:
        status = "OK" if result.ok else "ERROR"
        print(
            f"{status:5} | {result.method:40} | "
            f"{result.duration_ms:>6} ms | "
            f"{result.result_bytes:>9} bytes | "
            f"nodos={result.xml_node_count:<6}"
        )
        if result.error:
            print(f"      error: {result.error}")
        elif result.preview:
            print(f"      preview: {result.preview[:180]}")


def parse_args() -> argparse.Namespace:
    """Parsea argumentos CLI."""

    parser = argparse.ArgumentParser(
        description="Diagnostica métodos GBP de lectura para el integrador GBP -> TN."
    )
    parser.add_argument("--only-auth", action="store_true", help="Solo autentica.")
    parser.add_argument("--sku", help="SKU/código para resolver ID GBP.")
    parser.add_argument("--item-id", type=int, help="ID interno GBP para pruebas por artículo.")
    parser.add_argument(
        "--storage-id",
        type=int,
        default=-1,
        help="ID de depósito. Default: -1.",
    )
    parser.add_argument(
        "--price-list-id",
        type=int,
        help="ID de lista de precios para validar precio inicial.",
    )
    parser.add_argument(
        "--include-full-catalog",
        action="store_true",
        help="Incluye consultas potencialmente pesadas de catálogo completo.",
    )
    parser.add_argument(
        "--include-heavy-stock",
        action="store_true",
        help="Incluye benchmark pesado de stock completo con -1/-1.",
    )
    parser.add_argument(
        "--method",
        action="append",
        help="Ejecuta solo uno o más métodos concretos. Repetible.",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Guarda XML SOAP crudo en diagnostics/gbp/raw/.",
    )
    return parser.parse_args()


def main() -> None:
    """Punto de entrada CLI."""

    args = parse_args()
    config = load_config()
    results: list[DiagnosticResult] = []

    with httpx.Client(timeout=config.timeout_seconds) as client:
        token, auth_result = authenticate(client, config, args.save_raw)
        results.append(auth_result)

        if not args.only_auth:
            for spec in build_method_specs(args):
                result = call_method(
                    client=client,
                    config=config,
                    token=token,
                    spec=spec,
                    save_raw=args.save_raw,
                )
                results.append(result)

    jsonl_path = write_jsonl(results)
    csv_path = write_summary_csv(results)
    print_summary(results)
    print(f"\nJSONL: {jsonl_path}")
    print(f"CSV:   {csv_path}")


if __name__ == "__main__":
    main()
