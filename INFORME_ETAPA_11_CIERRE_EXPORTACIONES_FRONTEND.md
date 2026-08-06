# Etapa 11 — Cierre de exportaciones y frontend modular

## Objetivo

Cerrar la integración de Exportaciones Personalizadas GBP y reemplazar el JavaScript monolítico del panel enterprise por módulos con responsabilidades únicas.

## Cambios funcionales

- La búsqueda individual se realiza por `item_code` / SKU.
- El reporte 11 se identifica como interactivo y no se ejecuta por `wsExportDataById`.
- Los reportes 12, 13 y 14 son los únicos incluidos en la prueba SOAP.
- Una fila `GenerationError` ya no se considera una exportación válida: genera `ErrorExportacionGBP` con el detalle enviado por GBP.
- El resolvedor manual prioriza SKU y utiliza el reporte general 12.
- El panel expone los IDs 11–14, sucursal, flags de escritura y estado de credenciales sin mostrar secretos.

## Frontend modular

`app.js` es únicamente el punto de arranque. Las responsabilidades se separaron en:

- `core/dom.js`: acceso al DOM y renderizado básico.
- `core/http.js`: cliente HTTP y errores estructurados.
- `core/ui.js`: feedback visual, toasts y estado de botones.
- `features/navigation.js`: navegación y sidebar.
- `features/table-search.js`: filtrado visual de tablas.
- `features/exportaciones.js`: prueba de contratos y consulta por SKU.
- `features/jobs.js`: inicio y cancelación de trabajos.
- `features/pedidos.js`: importación de órdenes.
- `features/confirmations.js`: confirmaciones declarativas.

## Validaciones realizadas en el entorno de construcción

- Compilación Python completa.
- 86 pruebas aprobadas.
- Sintaxis validada de todos los módulos JavaScript con Node.js.
- Exclusión de `.env`, `.git`, `.venv`, bases locales, cachés y archivos compilados del entregable.

## Condición externa pendiente

El reporte 12 actualmente devuelve `GenerationError` desde GBP. El Integrador ahora lo detecta y muestra correctamente; el SQL del reporte debe corregirse en GBP con el detalle exacto de ese error antes de habilitar importación individual o masiva desde el reporte general.
