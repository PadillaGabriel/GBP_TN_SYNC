# Panel de decisiones de productos

Objetivo: gestionar productos auditados/importados sin activar procesos masivos ni schedulers.

## Dashboard

`GET /admin/dashboard`

Métricas nuevas:

- `productos_auditados`: productos normalizados/persistidos desde GBP.
- `productos_mapeados_tienda_nube`: productos con mapeo local GBP ↔ Tienda Nube.
- `productos_importados`: alias compatible de `productos_mapeados_tienda_nube`.
- `publicables_total`: productos con decisión `PUBLICABLE_AUTOMATICO`.
- `publicables_pendientes_importar`: publicables sin mapeo local en Tienda Nube.
- `bloqueados_total`: productos auditados no publicables.
- `bloqueados_importados_tienda_nube`: productos ya importados que hoy no cumplen reglas.
- `bloqueados_por_motivo`: conteo por decisión de bloqueo.

## Listado para decisiones

`GET /admin/decisiones/productos?estado=requiere_revision&limit=100&offset=0`

Valores de `estado`:

- `requiere_revision`: productos importados que hoy están bloqueados o con stock publicable menor o igual a 0.
- `bloqueado_importado`: productos con mapeo en Tienda Nube y decisión distinta de `PUBLICABLE_AUTOMATICO`.
- `bloqueado`: todos los productos bloqueados.
- `importado`: todos los productos con mapeo local en Tienda Nube.
- `publicable_pendiente`: productos publicables todavía no importados.
- `todos`: todos los productos auditados.
- cualquier decisión exacta, por ejemplo `NO_PUBLICAR_STOCK_SIN_DISPONIBLE`.

Cada item devuelve:

- SKU.
- ID GBP.
- título.
- categoría/subcategoría/marca.
- código proveedor.
- precio.
- stock publicable TN.
- decisión.
- motivos de bloqueo.
- largo de descripción.
- estado de mapeo en Tienda Nube.
- acciones disponibles.
- endpoints de acción.

## Ocultar producto en Tienda Nube

`POST /admin/decisiones/productos/{sku}/ocultar-tn?confirm=true`

Reglas:

- Con `DRY_RUN=true` no escribe en Tienda Nube.
- Con `confirm=false` no escribe en Tienda Nube.
- Con `DRY_RUN=false` y `confirm=true`, envía `published=false` a Tienda Nube.
- No borra el mapeo local.
- Actualiza `productos_tienda_nube.estado_publicacion = 'oculto_tn'`.
- Registra auditoría `TN_HIDE_PRODUCT_MANUAL`.

## Eliminar producto en Tienda Nube

`POST /admin/decisiones/productos/{sku}/eliminar-tn?confirm=true`

Reglas:

- Con `DRY_RUN=true` no escribe en Tienda Nube.
- Con `confirm=false` no escribe en Tienda Nube.
- Con `DRY_RUN=false` y `confirm=true`, ejecuta DELETE sobre el producto en Tienda Nube.
- No borra el mapeo local.
- Actualiza `productos_tienda_nube.estado_publicacion = 'eliminado_tn'`.
- Registra auditoría `TN_DELETE_PRODUCT_MANUAL`.

## Importación manual forzada

Sigue vigente:

`POST /sync/import/tienda-nube-manual?sku={sku}&forzar=true&confirm=true`

Uso: publicar manualmente un producto bloqueado cuando la decisión comercial lo justifique.
