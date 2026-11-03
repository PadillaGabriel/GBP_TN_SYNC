# Descubrimiento y vinculación de productos creados directamente en Tiendanube

## Alcance
- Lectura paginada de catálogo TN por API (100 productos/página).
- Reconciliación de cada variante contra `productos_fuente.sku` con igualdad exacta.
- Persistencia en `productos_tienda_nube` con `product_id`, `variant_id`, `producto_fuente_id`.
- No modifica imágenes, títulos, precios, descripciones ni stock externo.
- Crea eventos `DESCUBRIR_MAPEO_TN` para vínculos y conflictos, visibles en Auditoría.
- Nuevo job durable `DESCUBRIR_TN`, ejecutado por el worker existente.
- Ejecución manual desde Sincronización y diaria a las 03:00 UTC **solo si `STOCK_SCHEDULER_ENABLED` está habilitado y el proceso scheduler se ejecuta**.

## Protección de integridad
- Dos fases: primero recorre todas las páginas y detecta duplicados, después escribe mapeos.
- Un catálogo incompleto no produce nuevas vinculaciones. El máximo automático es 100 páginas (10.000 productos); el endpoint permite hasta 500 páginas.
- Un SKU ambiguo se envía a revisión, no se vincula.
- Un vínculo activo conflictivo no se reemplaza automáticamente.
- Una variante TN ya vinculada a otro SKU local no se reutiliza.
- Solo se vinculan SKU que constan en `productos_fuente`; la ausencia de un GBP local se informa en la estadística `sin_producto_gbp_local`.

## Operación
1. Verificar que estén configuradas credenciales TN y que la importación/auditoría GBP mantenga actualizado el catálogo local.
2. Ejecutar desde Sincronización: **Buscar y vincular productos**.
3. Consultar el job en Trabajos; revisar `vinculados`, `conflictos`, `sin_producto_gbp_local`, `incompleto`.
4. Comprobar un SKU en Productos y posteriormente ejecutar sincronización de stock existente con una prueba controlada.
5. Verificar programador de Railway y variable de `stock_scheduler_enabled` antes de asumir que se ejecutará automáticamente.

## Límites sin resolver
- No existe todavía un proceso que descubra un SKU presente en GBP pero ausente del catálogo local: primero debe incorporarse por la auditoría existente.
- No hay suscripción a webhook de creación/modificación de productos TN para descubrimiento inmediato; la frecuencia automática es diaria.
- Si el catálogo supera las 10.000 publicaciones, el barrido diario terminará `incompleto` y no efectuará vinculaciones. Debe aumentarse el rango/manual o diseñar un recorrido con checkpoint seguro.
- No se verificó contra credenciales productivas reales ni se ejecutó un despliegue en Railway.
