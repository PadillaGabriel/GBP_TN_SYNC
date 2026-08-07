# Mejora de resiliencia GBP y seguimiento de jobs

## Resiliencia GBP
- Reintentos controlados solo en `ClienteGBP`, cliente de lectura del módulo 16.
- 3 intentos totales por defecto.
- Backoff exponencial configurable: 1s, 2s entre los tres intentos.
- Reintenta errores de transporte transitorios (`ConnectTimeout`, `ReadTimeout`, `ConnectError`, `RemoteProtocolError`) y HTTP 429/502/503/504.
- No reintenta errores HTTP funcionales 4xx distintos de 429.
- Los clientes de escritura de pedidos GBP no fueron modificados para evitar duplicación de operaciones no idempotentes.
- Logging estructurado de retry y agotamiento de reintentos.

Variables:
- `GBP_RETRY_ATTEMPTS=3`
- `GBP_RETRY_BACKOFF_SECONDS=1.0`

## Jobs en tiempo real
- El repositorio serializa progreso estructurado y campos aplanados consistentes para el panel.
- La pantalla Trabajos consulta `/admin/panel/jobs` cada 1.2 segundos.
- Barra, porcentaje, estado, mensaje, procesados y conteos se actualizan sin recargar.
- Cancelación actualiza inmediatamente la vista.
- Trabajos iniciados desde el panel redirigen al centro de trabajos para seguimiento.
- La sincronización manual de stock informa avance por SKU durante el lote (5% a 95%, 100% al finalizar).

## Auditoría del panel Enterprise
- Sintaxis de todos los módulos JS validada con Node.
- Todas las plantillas Enterprise parseadas con Jinja2.
- Imports JS de `app.js` verificados.
- No quedan referencias visuales al panel legacy eliminado (`panel-legacy`, `/admin/panel/decisiones`, `static/admin`).
- Acciones revisadas: productos, categorías, importaciones, stock, reconciliación, pedidos y exportaciones.

## Quality gate ejecutado
- `python -m compileall -q app tests`: OK
- `pytest -q`: 107 passed
- Jinja Enterprise: OK
- JavaScript `node --check`: OK
- Ruff: no disponible en el entorno de generación; no se afirma ejecución.
