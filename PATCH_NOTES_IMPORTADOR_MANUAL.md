# Cambios aplicados - Importador manual flexible

## Objetivo
Mejorar el importador manual sin afectar la auditoria/importacion masiva ni la actualizacion de stock.

## Cambios principales

### 1. Validacion parametrizada
Archivo: `app/application/services/producto_validation_service.py`

- Se agrego `exigir_item_web: bool = True`.
- Se agrego `modo_manual_flexible: bool = False`.
- En modo manual flexible no bloquea por:
  - imagen faltante
  - descripcion faltante
  - precio faltante
  - stock faltante
  - item_web falso/no confirmado
- En auditoria/importacion masiva el comportamiento estricto se mantiene por default.

### 2. Cliente GBP mas robusto
Archivo: `app/infrastructure/gbp/client.py`

- Se agrego normalizacion conservadora de SKU sin eliminar letras.
- Se agrego lectura tolerante de nombres de columnas (`item_id`, `ItemID`, `intItemID`, etc.).
- Se reforzo `obtener_item_id_por_codigo` con logs de `row_keys` y `row_preview`.
- Se agrego/fortalecio fallback de ficha basica por `ItemBasicData_funGetXMLData`.

### 3. Importador manual flexible
Archivo: `app/application/services/tienda_nube_import_service.py`

- El flujo manual usa `_obtener_producto_manual_flexible`.
- Si GBP no devuelve ficha completa o el normalizador no puede armar producto completo, crea un `Producto` minimo manual.
- El producto minimo se arma con:
  - SKU informado
  - item_id resuelto
  - titulo basico
  - descripcion basica
  - precio `None` => payload con `0.00`
  - stock `None` => payload con `0`
- Esto evita ventas accidentales hasta completar datos manualmente en Tienda Nube.

## No modificado

- Logica de stock operativa.
- Auditoria GBP.
- Importacion masiva estricta.
- Payload builder existente.
- Modelos de dominio.

## Validacion ejecutada

```bash
python -m pytest -q
```

Resultado:

```text
30 passed
```

## Nota de seguridad operativa

El ZIP entregado no incluye `.env`, `.git`, `__pycache__` ni cache de pytest.
