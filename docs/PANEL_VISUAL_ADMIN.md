# Panel visual admin

URL principal:

```text
/admin/panel
```

Vista de decisiones:

```text
/admin/panel/decisiones?estado=requiere_revision&limit=100
```

## Función

Permite revisar visualmente productos auditados, bloqueados, importados y pendientes, con acciones manuales sobre Tienda Nube.

## Componentes

- `app/templates/admin/panel_decisiones.html`: estructura HTML del panel.
- `app/static/admin/panel.css`: diseño visual del panel.
- `app/static/admin/panel.js`: confirmaciones para acciones manuales.
- `app/api/routes_admin.py`: rutas HTML y endpoints JSON existentes.

## Filtros

- `requiere_revision`
- `bloqueado_importado`
- `publicable_pendiente`
- `importado`
- `bloqueado`
- `todos`
- `NO_PUBLICAR_STOCK_SIN_DISPONIBLE`
- `NO_PUBLICAR_SIN_DESCRIPCION_WEB`
- `PUBLICABLE_AUTOMATICO`

## Búsqueda

El parámetro `q` busca por:

- SKU
- título
- categoría
- subcategoría
- marca
- código proveedor
- ID de producto en Tienda Nube

Ejemplo:

```text
/admin/panel/decisiones?estado=todos&q=1689&limit=100
```

## Acciones

Las acciones del panel usan confirmación visual antes de ejecutar:

- Ocultar: despublica el producto en Tienda Nube y conserva el mapeo local.
- Eliminar TN: elimina el producto en Tienda Nube y conserva auditoría local.
- Importar forzado: importa o actualiza manualmente aunque el producto esté bloqueado.

Con `DRY_RUN=true`, no se escribe en Tienda Nube.
Con `DRY_RUN=false`, las acciones confirmadas pueden escribir en Tienda Nube.
