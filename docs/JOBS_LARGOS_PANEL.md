# Jobs largos desde panel

Se agregaron procesos en segundo plano para evitar requests HTTP bloqueantes cuando se quiere operar sobre todo el universo de productos.

## Panel visual

URL:

```text
/admin/panel
```

Acciones nuevas:

- `Auditar todo`: audita todos los productos GBP pendientes con imagen Website, por tandas.
- `Importar todo`: importa todos los productos `PUBLICABLE_AUTOMATICO` pendientes, por tandas.
- `Importar SKU puntual`: busca un SKU en GBP, lo valida, lo persiste y lo importa/actualiza en Tienda Nube.

El panel muestra un popup de progreso consultando el estado del job cada pocos segundos.

## Endpoints de jobs

```http
POST /sync/jobs/audit-all?batch_limit=200&concurrency=3
GET  /sync/jobs/{job_id}
```

```http
POST /sync/jobs/import-all?batch_limit=50
GET  /sync/jobs/{job_id}
```

Estados posibles:

```text
PENDIENTE
EN_PROCESO
FINALIZADO
FINALIZADO_CON_ERRORES
ERROR
```

El progreso se guarda en `sync_jobs.error_mensaje` como JSON para no requerir migración de esquema.

## Importación directa por SKU

```http
POST /sync/import/tienda-nube-sku?sku=6130BL&confirm=true&forzar=false
```

Reglas:

- Busca el `item_id` en GBP por SKU.
- Consulta detalle, imágenes, precio y stock.
- Valida reglas de publicación.
- Persiste producto, validación y stock.
- Si está publicable, importa/actualiza en Tienda Nube.
- Si está bloqueado, solo importa si `forzar=true`.
- Si `DRY_RUN=true`, no escribe aunque `confirm=true`.

## Límites operativos recomendados

Auditoría total:

```text
batch_limit=200
concurrency=3
```

Importación total:

```text
batch_limit=50
```

Los refresh automáticos futuros deben ser más chicos y específicos: stock por tandas livianas, sin reimportar descripciones/precios salvo proceso manual.
