# Cómo validar métodos GBP

## 1. Configurar `.env`

Completar estas variables:

```env
GBP_USERNAME=
GBP_PASSWORD=
GBP_COMPANY_ID=
GBP_WEB_SERVICE_ID=
GBP_TIMEOUT_SECONDS=30
```

No versionar `.env`.

## 2. Probar autenticación

```bash
python scripts/diagnosticar_gbp_metodos.py --only-auth
```

Resultado esperado: `AuthenticateUser` en estado `OK`.

## 3. Probar métodos livianos y catálogos auxiliares

```bash
python scripts/diagnosticar_gbp_metodos.py
```

Esto ejecuta:

- marcas;
- categorías;
- subcategorías;
- unidades;
- listas de precio;
- datos básicos de artículos actualizados.

## 4. Probar un producto real

```bash
python scripts/diagnosticar_gbp_metodos.py --sku TU_SKU --item-id TU_ITEM_ID
```

Esto valida:

- SKU/código -> ID GBP;
- ficha completa por ID;
- stock por artículo;
- imágenes por artículo;
- URLs de imágenes Website IV.

## 5. Probar precio inicial

```bash
python scripts/diagnosticar_gbp_metodos.py --item-id TU_ITEM_ID --price-list-id TU_LISTA
```

El precio no forma parte de la sincronización frecuente. Solo se usa en importación inicial o actualización completa manual.

## 6. Probar cargas pesadas solo de forma controlada

```bash
python scripts/diagnosticar_gbp_metodos.py --include-full-catalog
python scripts/diagnosticar_gbp_metodos.py --include-heavy-stock
```

Estas pruebas pueden devolver respuestas grandes. No usarlas como scheduler frecuente sin medir.

## 7. Archivos generados

```text
diagnostics/gbp/gbp_diagnostic_results.jsonl
diagnostics/gbp/gbp_diagnostic_summary.csv
diagnostics/gbp/raw/   # solo si se usa --save-raw
```

## 8. Decisión técnica después de medir

Para cada método completar:

- si devuelve los campos esperados;
- si el XML es estable;
- si la latencia es aceptable;
- si conviene consultarlo masivamente o por artículo;
- si debe entrar al import inicial, cache auxiliar o scheduler de stock;
- si debe quedar descartado.
