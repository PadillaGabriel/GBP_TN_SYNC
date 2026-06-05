# Panel de administración final

## Vistas

- Dashboard
- Productos
- Candidatos Web
- Publicables
- Bloqueados
- Sincronización de stock
- Jobs
- Auditoría
- Configuración de depósitos

## Dashboard

Debe mostrar:

```text
Total productos GBP
Candidatos con imagen Website
Publicables automáticos
Bloqueados por falta de descripción web
Bloqueados por falta de precio
Bloqueados por stock no consultable
Importados a Tienda Nube
Jobs fallidos
Última sincronización de stock
```

## Productos

Columnas mínimas:

```text
SKU
ID GBP
Título
Categoría
Subcategoría
Marca
Código proveedor
item_web
Descripción Website
Precio online
Stock disponible
Decisión
Motivos
Acciones
```

## Bloqueados

Motivos posibles:

```text
SIN_IMAGEN_WEBSITE
ITEM_WEB_NO_VALIDO
ITEM_DISABLED
ITEM_NOT_FOR_SALE
SIN_DESCRIPCION_WEB
SIN_PRECIO_ONLINE
STOCK_NO_CONSULTABLE
SIN_SKU
SIN_TITULO
```

## Configuración de depósitos

El stock Tienda Nube se calcula solo con depósitos habilitados.

```text
stor_id
nombre
habilitado_tn
observación
```
