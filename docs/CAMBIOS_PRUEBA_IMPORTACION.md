# Cambios incorporados tras primera prueba de importación

## Reglas nuevas

- Producto con stock publicable `0` o menor no queda como `PUBLICABLE_AUTOMATICO`.
- Nuevo motivo: `NO_PUBLICAR_STOCK_SIN_DISPONIBLE`.
- El código de proveedor GBP (`item_vendorCode`) se envía como `barcode`/código universal de la variante en Tienda Nube.
- La descripción web completa se conserva en base como `TEXT` y se envía completa en `description.es`.
- Categoría y subcategoría GBP se aseguran en Tienda Nube antes de crear o actualizar el producto.
- La importación controlada por lote excluye SKUs ya mapeados en `productos_tienda_nube`.
- Si el SKU ya existe en Tienda Nube, el adaptador actualiza el producto existente en lugar de crear duplicado.

## Endpoints nuevos

```http
GET /admin/productos/importados?limit=100&offset=0
```

Lista productos con mapeo GBP ↔ Tienda Nube.

```http
GET /admin/productos/bloqueados?limit=100&offset=0
```

Lista productos bloqueados, motivo de bloqueo, stock publicable y endpoint sugerido para importación manual.

```http
POST /sync/import/tienda-nube-manual?sku=3556&confirm=true&forzar=true
```

Importa o actualiza un producto puntual. Respeta `DRY_RUN`; si el producto está bloqueado requiere `forzar=true`.

## Seguridad operativa

Mantener en Render hasta revisión:

```env
DRY_RUN=true
STOCK_SCHEDULER_ENABLED=false
IMPORT_SCHEDULER_ENABLED=false
```

## Corrección de descripción Website larga

Se corrigió el parser de XML GBP para no truncar `WebSite_Description` cuando GBP devuelve HTML escapado dentro del `NewDataSet`.

Problema detectado:

```text
ElementTree guardaba en child.text solo el texto anterior al primer tag interno.
Ejemplo: texto antes de <br>, <p> o <div>.
El contenido posterior quedaba en .tail y se perdía.
```

Corrección:

```text
parse_dataset_tables ahora usa extract_node_full_text(child)
```

La nueva función recorre texto, hijos y tails del nodo, preservando el contenido completo de descripciones largas.

Tests agregados:

```text
tests/test_gbp_description_parser.py
```
