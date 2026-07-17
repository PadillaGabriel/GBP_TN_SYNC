# Corrección final: Tienda Nube 422 y actualización enterprise-safe

## Objetivo

Eliminar el error `422 Unprocessable Entity` al actualizar productos existentes en Tienda Nube y mejorar la trazabilidad de errores sin afectar el flujo GBP -> Tienda Nube ni la sincronización de stock.

## Problema raíz

El integrador actualizaba un producto existente usando el payload completo de creación contra:

```text
PUT /products/{product_id}
```

Ese payload incluía `variants` e `images`. En Tienda Nube, precio, stock, SKU y barcode pertenecen a la variante; reenviar variantes completas durante un update de producto puede provocar errores 422, especialmente si existen variantes previas, combinaciones repetidas, stock decimal, precio con demasiados decimales o imágenes ya cargadas.

## Cambios aplicados

### 1. Separación de responsabilidades por endpoint

Archivo:

```text
app/infrastructure/tienda_nube/adapter.py
```

Nuevo comportamiento:

- Producto nuevo:
  - `POST /products`
  - incluye nombre, descripción, categorías, imágenes y variante principal.
- Producto existente:
  - `PUT /products/{product_id}` solo con nombre, descripción y categorías.
  - `PUT /products/{product_id}/variants/{variant_id}` para SKU, precio, stock y barcode.
- Imágenes:
  - se envían solo al crear producto.
  - no se reenvían en update para evitar duplicados y 422.

### 2. Payloads específicos por operación

Archivo:

```text
app/infrastructure/tienda_nube/payload_builder.py
```

Funciones nuevas/separadas:

- `build_create_product_payload`
- `build_update_product_payload`
- `build_create_variant_payload`
- `build_update_variant_payload`

Reglas:

- `price` se formatea a 2 decimales.
- `stock` se envía como entero no negativo.
- `stock_management=True` cuando se envía stock.
- `barcode` no se envía si está vacío o `None`.
- En updates no se pisa precio/stock con `0` si GBP no informó datos.

### 3. Cliente Tienda Nube con errores explicables

Archivo:

```text
app/infrastructure/tienda_nube/client.py
```

Mejoras:

- Se agregó `_raise_for_status` centralizado.
- Los errores HTTP ahora conservan:
  - status code
  - URL
  - response body de Tienda Nube
  - request body enviado
- Se agregaron métodos explícitos:
  - `create_variant`
  - `update_variant`

### 4. Error controlado de Tienda Nube

Archivo:

```text
app/domain/errors.py
```

Nuevo error:

```python
TiendaNubeHTTPError
```

Permite que el panel muestre el detalle real del error 422 en vez de un mensaje genérico.

### 5. Job manual con detalle de error 422

Archivo:

```text
app/application/jobs/bulk_jobs.py
```

Si Tienda Nube responde 422, el panel ahora puede mostrar:

- `tn_status_code`
- `tn_url`
- `tn_response`
- `tn_request`

### 6. Tests agregados

Archivos:

```text
tests/test_tienda_nube_payload.py
tests/test_tienda_nube_adapter_update.py
```

Cobertura nueva:

- El update de producto no incluye variantes ni imágenes.
- El update de variante formatea precio/stock correctamente.
- No se pisa precio/stock con cero cuando faltan datos en actualización.
- El adaptador actualiza producto y variante por separado.

## Validación ejecutada

```bash
python -m compileall -q app scripts
python -m pytest -q
```

Resultado:

```text
36 passed
```

## Archivos modificados

```text
app/application/jobs/bulk_jobs.py
app/domain/errors.py
app/infrastructure/tienda_nube/adapter.py
app/infrastructure/tienda_nube/client.py
app/infrastructure/tienda_nube/payload_builder.py
tests/test_tienda_nube_payload.py
tests/test_tienda_nube_adapter_update.py
```

## Archivos que se pueden limpiar luego de validar

No son necesarios en producción:

```text
diagnostics/
__pycache__/
.pytest_cache/
*.pyc
```

Notas antiguas de parche pueden moverse a `docs/` o eliminarse una vez validada esta versión:

```text
PATCH_NOTES_IMPORTADOR_MANUAL.md
PATCH_NOTES_ORQUESTADOR_FUENTES_GBP.md
PATCH_NOTES_FINAL_INTEGRADOR_GBP_TN.md
```

Se recomienda conservar:

```text
scripts/diagnosticar_gbp_metodos.py
scripts/probar_fuentes_producto_gbp.py
```

porque siguen siendo útiles para auditar diferencias entre métodos GBP.
