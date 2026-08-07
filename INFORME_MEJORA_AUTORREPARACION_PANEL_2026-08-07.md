# Mejora de autorreparación de stock y saneamiento del panel

## Alcance

- Autorreparación de vínculos Tiendanube ante HTTP 404 durante stock.
- Retiro automático de mapeos obsoletos para evitar errores recurrentes.
- Auditoría explícita `MAPEO_TN_REPARADO` / `MAPEO_TN_OBSOLETO`.
- Reintento único de stock luego de reparar `product_id` / `variant_id`.
- Panel enterprise con menú de acciones funcional en Productos.
- Corrección de información de producto: `id_sistema_gbp`, precio cero, stock y vínculo TN.
- Mejor tratamiento visual de textos largos y decisiones.
- Reconciliación manual de vínculos desde Sincronización.
- Eliminación del panel legacy, template y assets sin consumidores funcionales.
- Favicon enterprise para eliminar el 404 cosmético.
- Corrección del path visual de `scripts\\auditar_calidad.ps1`.

## Regla de seguridad

La sincronización de stock nunca crea un producto como consecuencia de un 404. Primero busca el SKU vigente en Tiendanube. Si existe, corrige el mapeo y reintenta una vez. Si no existe o la variante no puede resolverse de forma inequívoca, marca el vínculo como `vinculacion_obsoleta` y lo excluye de futuros lotes automáticos.

## Validación ejecutada

- `python -m compileall -q app tests`: OK.
- Compilación de todas las plantillas Jinja enterprise: OK.
- `pytest -q`: 102 pruebas aprobadas.
- Ruff no estaba instalado en el entorno local usado para preparar este entregable, por lo que no se declara ejecutado.
