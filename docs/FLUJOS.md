# Flujos principales

## Importación inicial

GBP producto completo → normalizador → modelo interno → Tienda Nube → auditoría.

Incluye precio, descripción, medidas, fotos, categoría y stock inicial.

## Sincronización frecuente

GBP stock → comparación local → actualización Tienda Nube solo si cambió → auditoría.

No actualiza precio.
No actualiza descripción.
No actualiza fotos.
No actualiza categoría.
No actualiza medidas.

## Panel admin

Acciones mínimas:

- Refrescar stock por SKU.
- Importar producto completo por SKU.
- Ver auditoría.
- Ver productos importados.
- Reintentar errores cuando se implemente cola de jobs.
