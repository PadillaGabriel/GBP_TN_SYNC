# Jobs visibles del panel

Todas las operaciones largas o potencialmente lentas del panel deben ejecutarse como job persistido en `sync_jobs`.

## Objetivos

- Mostrar popup con barra de progreso.
- Permitir cerrar el popup sin perder el proceso.
- Permitir volver a abrir el proceso desde la sección "Procesos en segundo plano".
- Evitar depender de logs de Render para saber si una acción sigue activa.
- Guardar detalle operativo en base de datos.

## Operaciones cubiertas

- Auditar próximos productos.
- Auditar todo.
- Importar pendientes.
- Importar todo.
- Importar SKU puntual.
- Sincronizar stock por lote.
- Sincronizar stock por SKU.
- Normalizar categorías.
- Reauditar bloqueados por descripción.
- Reauditar bloqueados por stock sin disponible.
- Reauditar bloqueados por stock no consultable.

## Categorías

La creación/asignación de categorías se normaliza durante la importación. La acción "Normalizar categorías" queda como herramienta correctiva final, no como parte normal del flujo.

La protección principal agregada es un lock de creación de categorías para evitar duplicados por importaciones concurrentes.

## Reauditoría

La reauditoría por decisión consulta GBP en vivo, persiste el nuevo estado del producto y registra en `sync_audit`:

- decisión anterior
- decisión nueva
- motivos actuales
- stock
- precio
- largo de descripción
