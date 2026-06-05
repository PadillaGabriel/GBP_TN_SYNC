# Panel visual de decisiones administrativas

## URL principal

```text
/admin/panel
```

Redirige a:

```text
/admin/panel/decisiones?estado=requiere_revision&limit=100
```

## Vistas disponibles

- `requiere_revision`: productos importados que hoy requieren una decisión.
- `bloqueado_importado`: productos ya mapeados en Tienda Nube pero actualmente bloqueados por reglas de validación.
- `publicable_pendiente`: productos publicables todavía no importados.
- `importado`: productos con mapeo local hacia Tienda Nube.
- `bloqueado`: productos bloqueados por cualquier motivo.
- `todos`: todos los productos auditados.
- `NO_PUBLICAR_STOCK_SIN_DISPONIBLE`: productos bloqueados por stock 0 o menor.
- `NO_PUBLICAR_SIN_DESCRIPCION_WEB`: productos bloqueados por falta de descripción web.
- `PUBLICABLE_AUTOMATICO`: productos publicables.

## Acciones visuales

Desde cada fila el panel puede ejecutar:

- Ocultar en Tienda Nube.
- Eliminar en Tienda Nube.
- Importar manualmente forzado.

Las acciones usan `confirm=True` internamente porque el formulario visual ya representa una decisión explícita del operador. Si `DRY_RUN=true`, no se escribe en Tienda Nube. Si `DRY_RUN=false`, las acciones escriben realmente.

## Endpoints HTML agregados

```text
GET  /admin/panel
GET  /admin/panel/decisiones
POST /admin/panel/decisiones/{sku}/ocultar-tn
POST /admin/panel/decisiones/{sku}/eliminar-tn
POST /admin/panel/decisiones/{sku}/importar-manual
```

## Endpoints JSON conservados

Los endpoints JSON previos siguen disponibles:

```text
GET  /admin/dashboard
GET  /admin/decisiones/productos
POST /admin/decisiones/productos/{sku}/ocultar-tn?confirm=true
POST /admin/decisiones/productos/{sku}/eliminar-tn?confirm=true
POST /sync/import/tienda-nube-manual?sku={sku}&forzar=true&confirm=true
```
