# Auditoría `item_web` GBP

## Objetivo

Validar si `item_web` sirve como criterio principal para decidir qué productos de GBP deben importarse/publicarse en Tienda Nube.

Regla candidata:

```text
producto_publicable = item_web == true
```

Exclusiones obligatorias:

```text
item_disabled == true  -> no publicar
item_not4Sale == true  -> no publicar
```

## Por qué es necesario

GBP tiene aproximadamente 13.000 productos, pero no todos están publicados online. Si `item_web=true` aparece en casi todos, el campo está mal mantenido en origen y hay que corregirlo en GBP antes de automatizar la importación masiva.

## Script

```bash
python scripts/auditar_item_web.py --source basic
```

Este modo usa `ItemBasicData_funGetXMLData(bitOnlyNewOrUpdated=False)` y genera conteos generales.

Salida:

```text
diagnostics/gbp/item_web/item_web_audit_YYYYMMDD_HHMMSS.csv
diagnostics/gbp/item_web/item_web_audit_summary_YYYYMMDD_HHMMSS.json
```

## Auditoría por ficha completa

Si el catálogo básico no trae `item_web` o se quiere validar por `wsItem_funGetXMLDataById`:

```bash
python scripts/auditar_item_web.py --source detail --limit 200 --concurrency 5
```

Para auditar todos los productos por detalle:

```bash
python scripts/auditar_item_web.py --source detail --concurrency 5
```

Usar este modo con cuidado porque consulta una ficha completa por producto.

## Interpretación

### Caso correcto

```text
item_web=true  ≈ cantidad real de productos publicados online
item_web=false ≈ productos no publicados
```

Decisión:

```text
usar item_web como criterio principal
```

### Caso incorrecto

```text
item_web=true ≈ 13.000 productos
```

Decisión:

```text
no automatizar importación masiva todavía
corregir tilde en GBP
usar importación inicial por lista controlada de SKUs publicados
```

### Caso indeterminado

```text
item_web vacío o campo ausente
```

Decisión:

```text
validar por ficha completa con --source detail
```

## Columnas del CSV

```text
item_id
item_code
item_desc
item_web
item_disabled
item_not4_sale
image_existing
has_website_image
has_website_description
cat_desc
subcat_desc
brand_desc
decision
source
duration_ms
error
```

## Decisiones posibles

```text
PUBLICABLE_ITEM_WEB_TRUE
NO_PUBLICABLE_ITEM_WEB_FALSE
NO_PUBLICABLE_ITEM_DISABLED
NO_PUBLICABLE_ITEM_NOT4SALE
CANDIDATO_POR_IMAGEN_WEB_SIN_ITEM_WEB
NO_DECIDIBLE_BASIC_SIN_ITEM_WEB
NO_PUBLICABLE_SIN_SENAL_WEB
ERROR_CONSULTA_DETALLE
ERROR_SIN_DATOS
```

## Corrección de XML inválido en catálogo básico

Si `ItemBasicData_funGetXMLData` devuelve un XML con caracteres inválidos o ampersands sin escapar, el script sanitiza el XML antes de parsearlo.

Si el parseo vuelve a fallar, guarda contexto en:

```text
diagnostics/gbp/item_web/xml_parse_error_context_YYYYMMDD_HHMMSS.txt
```

Ese archivo sirve para identificar el producto/campo que viene mal desde GBP.
