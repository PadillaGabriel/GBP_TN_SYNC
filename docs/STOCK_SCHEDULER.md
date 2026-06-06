# Scheduler de stock

## Objetivo

Sincronizar únicamente stock GBP -> Tienda Nube para productos ya importados y mapeados.

No actualiza:

- precio
- descripción
- imágenes
- categorías
- publicación
- datos comerciales
- productos nuevos

## Reglas

- Fuente: GBP / GlobalBluePoint.
- Depósito ecommerce: `ECOMMERCE_STORAGE_IDS`, actualmente `18`.
- Campo utilizado: `Stock`.
- Stock negativo: se envía como `0`.
- Stock `0`: válido.
- Stock no consultable: no actualiza Tienda Nube y registra auditoría.
- Solo opera sobre mapeos activos en `productos_tienda_nube`.
- No toca mapeos `eliminado_tn` ni `eliminado_externo`.

## Endpoints manuales

```http
GET /sync/stock/status
POST /sync/stock/run-now?limit=100
POST /sync/stock/run-sku?sku=6130BL
```

## Panel

Desde `/admin/panel`:

- `Sync stock 50`
- `Sync stock 200`
- `Sync SKU`

## Scheduler

Activación en Render:

```env
STOCK_SCHEDULER_ENABLED=true
STOCK_SYNC_INTERVAL_MINUTES=30
STOCK_SYNC_BATCH_SIZE=100
IMPORT_SCHEDULER_ENABLED=false
```

## Secuencia recomendada

1. Ejecutar manualmente:

```http
POST /sync/stock/run-now?limit=20
```

2. Validar resultado:

- `errores=0`
- `stock_no_consultable` controlado
- `actualizados` razonable
- `sin_cambios` razonable

3. Ejecutar lote mayor:

```http
POST /sync/stock/run-now?limit=100
```

4. Activar scheduler con intervalo de 30 minutos.

## Auditoría

Cada ejecución registra:

- `STOCK_SYNC_RUN_NOW`
- `STOCK_SYNC_SKU`

Estados por SKU:

- `ACTUALIZADO`
- `SIN_CAMBIOS`
- `SIMULADO`
- `STOCK_NO_CONSULTABLE`
- `ERROR`
