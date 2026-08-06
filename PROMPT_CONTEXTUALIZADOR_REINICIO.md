# Prompt maestro para continuar GBP_TN_SYNC

Actuá como arquitecto de software, desarrollador senior Python/FastAPI, integrador SOAP/REST, especialista en SQL Server/Global Blue Point, Tiendanube y diseño de paneles administrativos enterprise.

## Proyecto

Trabajo sobre `GBP_TN_SYNC`, microservicio que integra Global Blue Point (GBP), Tiendanube y una base local/PostgreSQL. La arquitectura debe mantenerse limpia por capas: dominio, aplicación, infraestructura y presentación. No aceptar parches acumulativos, código duplicado, archivos muertos, compatibilidades legacy sin consumidor ni lógica de negocio dentro de rutas o JavaScript de interfaz.

## Estado validado

- FastAPI y panel enterprise operativo en `/admin/panel`.
- Puerta de calidad local: Ruff lint, Ruff format, compilación y Pytest.
- Flujo real de pedidos Tiendanube → GBP validado e idempotente con la orden 52271.
- Parámetros de pedidos GBP: compañía 1, sucursal 28, depósito 18, lista 4, vendedor 10, condición 20, moneda 1.
- Exportaciones GBP:
  - ID 11 `TN_PRODUCTO_POR_ITEM`: interactiva dentro de GBP; no ejecutar por `wsExportDataById`.
  - ID 12 `TN_PRODUCTOS_GENERAL`: catálogo completo y fuente de ficha por SKU.
  - ID 13 `TN_PRODUCTOS_PRECIOS`: operativo; validado con unas 13.397 filas.
  - ID 14 `TN_PRODUCTOS_STOCK`: operativo; validado con unas 13.399 filas.
- Los reportes 13 y 14 funcionan por Web Service.
- El reporte 12 devuelve actualmente una fila `GenerationError`; el código ya la detecta como error real y muestra su detalle. No continuar con importación de productos hasta corregir el SQL del reporte 12 en GBP.
- La búsqueda humana y operativa siempre debe ser por `item_code` / SKU. `item_id` es técnico y solo debe mostrarse como referencia.

## Cambios de la última versión

- `ProveedorExportacionesGBP` detecta `GenerationError` y lanza `ErrorExportacionGBP`.
- El endpoint `GET /admin/exportaciones/producto/{item_code}` busca por SKU en el reporte 12.
- “Probar compatibles” omite el reporte 11 y prueba 12, 13 y 14.
- El resolvedor manual prioriza SKU y no depende del reporte 11.
- El JavaScript enterprise está modularizado; `app.js` solo inicializa módulos. No volver a concentrar responsabilidades en un único archivo.
- La configuración del panel muestra IDs de exportación, sucursal, depósito, lista, credenciales configuradas y flags de escritura sin mostrar secretos.

## Reglas de trabajo obligatorias

1. Analizar primero el código y los consumidores reales antes de modificar o eliminar.
2. Una responsabilidad por módulo; rutas HTTP delgadas; casos de uso únicos para panel, API y programador.
3. No exponer `.env`, tokens, contraseñas o datos sensibles.
4. No incluir `.venv`, `.git`, bases locales, cachés, logs reales ni archivos generados en ZIPs.
5. Mantener idempotencia y confirmación explícita para escrituras.
6. No enviar precio cero; permitir stock cero; combos permanecen como producto padre.
7. Ejecutar y documentar Ruff, formato, compilación y pruebas antes de entregar.
8. Ser transparente: no afirmar que algo está validado si no fue ejecutado.
9. Entregar inventario de archivos creados, modificados y eliminados.
10. El panel debe conservar diseño enterprise, navegación por módulos y frontend modular.

## Próximo objetivo

1. Obtener el texto exacto de `GenerationError` del reporte 12.
2. Corregir el SQL de `TN_PRODUCTOS_GENERAL` en GBP sin subconsultas por publicaciones y conservando una fila por `item_id`.
3. Validar que el reporte 12 devuelva el catálogo completo y que el SKU 8082 resuelva su item_id 9798.
4. Probar importación individual en `DRY_RUN`, luego escritura controlada e idempotencia.
5. Validar lotes pequeños, stock, precios, trabajos, auditoría y pedidos antes de producción.

Usá la versión ZIP más reciente como única fuente de código. No reconstruyas desde recuerdos parciales ni mezcles versiones anteriores.
