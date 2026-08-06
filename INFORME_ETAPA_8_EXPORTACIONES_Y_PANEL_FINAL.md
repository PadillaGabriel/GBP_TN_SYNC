# Etapa 8 — Exportaciones GBP y panel administrativo

## Fuente productiva de productos

Se incorporó un acceso único a las Exportaciones Personalizadas GBP:

- 11: `TN_PRODUCTO_POR_ITEM`
- 12: `TN_PRODUCTOS_GENERAL`
- 13: `TN_PRODUCTOS_PRECIOS`
- 14: `TN_PRODUCTOS_STOCK`

La importación de ficha y la sincronización de stock dejan de depender de llamadas SOAP dispersas por artículo. El cliente común ejecuta `wsExportDataById`, renueva la autenticación cuando corresponde, normaliza el dataset y permite resolver por `item_id` o SKU.

## Panel

El panel ahora expone:

- IDs de las cuatro exportaciones activas;
- diagnóstico conjunto de contratos y tiempos;
- previsualización completa de una ficha por `item_id`;
- fila cruda GBP y objeto normalizado;
- descripción, clasificación e IDs de producto/variante en la tabla principal;
- estado operativo existente de auditorías, jobs, importaciones, stock y mantenimiento.

## Seguridad operativa

- No se incorporó `.env` al entregable.
- La ficha completa no consulta publicaciones ni atributos de Mercado Libre.
- El stock masivo se consulta una sola vez por ejecución y se indexa por `item_id`.
- Se mantiene `DRY_RUN` y confirmación para escrituras en Tienda Nube.
- Los combos siguen representados por el SKU padre y usan el stock calculado por GBP.

## Verificación

- Compilación completa de `app`: correcta.
- Suite automatizada: `83 passed`.
