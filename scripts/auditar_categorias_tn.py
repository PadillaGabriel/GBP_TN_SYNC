"""Vista previa NO DESTRUCTIVA de duplicados de categorías existentes en Tiendanube.

Uso: python -m scripts.auditar_categorias_tn --output reporte_categorias.csv
No consulta ni modifica productos; los IDs sugeridos requieren validación humana.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
from collections import defaultdict
from pathlib import Path

from app.configuracion import obtener_configuracion
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube
from app.infraestructura.tienda_nube.utilidades_categorias import normalize_category_key


def detectar_duplicados(categories: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for category in categories:
        name = AdaptadorTiendaNube._category_es_name(category)
        cat_id = AdaptadorTiendaNube._extract_id(category)
        if cat_id is None or not normalize_category_key(name):
            continue
        parent_id = AdaptadorTiendaNube._extract_parent_id(category)
        groups[(parent_id or 0, normalize_category_key(name))].append((cat_id, name))
    report = []
    for (parent, key), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        ids = sorted(id_ for id_, _ in rows)
        report.append({
            "parent_id": parent or "",
            "clave": key,
            "ids_existentes": ",".join(map(str, ids)),
            "id_candidato": ids[0],
            "cantidad": len(ids),
            "estado": "REVISION_MANUAL_OBLIGATORIA",
        })
    return report


async def main(output: Path) -> None:
    cfg = obtener_configuracion()
    client = ClienteTiendaNube(
        base_url=cfg.tienda_nube_base_url,
        store_id=cfg.tienda_nube_store_id,
        access_token=cfg.tienda_nube_access_token,
        timeout_seconds=cfg.tienda_nube_timeout_seconds,
    )
    rows = detectar_duplicados(await client.list_categories())
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["parent_id", "clave", "ids_existentes", "id_candidato", "cantidad", "estado"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Grupos duplicados: {len(rows)}. Vista previa: {output}")
    print("Sin modificaciones en Tiendanube ni PostgreSQL.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.output))
