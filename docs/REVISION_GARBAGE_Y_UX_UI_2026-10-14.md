# GBP_TN_SYNC — Auditoría de limpieza y rediseño UX/UI v2

**Fecha:** 2026-10-14  
**Punto de partida:** ZIP del proyecto + parche incremental de refactorización Railway 2026-10-13 (aprobado).  
**Cobertura:** arquitectura de presentación, assets JS/CSS, navegación, estados de jobs, auditabilidad, configuración, residuos y compatibilidad del backend.  
**Estado:** implementado y validado en entorno aislado; **despliegue productivo NO realizado**.

## 1. Alcance y método

1. Reconstrucción íntegra de la versión de trabajo superponiendo el ZIP de refactorización aprobado al ZIP original; comparación por hash SHA-256.
2. Inventario de módulos Python, templates Jinja, assets ES Modules, puntos de entrada, endpoints y consumidores mediante búsquedas estáticas.
3. Revisión de dependencias entre HTML, JS, rutas, repositorios y configuración. Clasificación por evidencia: eliminación confirmada, limpieza interna, potencialmente obsoleto y conservación obligatoria.
4. Evaluación heurística UX: información operacional, jerarquía, navegación, accesibilidad, estados vacíos, datos sensibles, responsive, retroalimentación, operaciones destructivas y visibilidad de errores.
5. Refactorización de presentación sin nuevas dependencias frontend, sin modificar integraciones GBP/TN ni máquina de estados del worker.
6. Verificación local: tests Python, parsing de CSS, chequeo sintáctico JS, renderizado HTML de las diez rutas y simulación de interacciones JS en navegador aislado.

**Límite metodológico:** una búsqueda estática no puede demostrar ausencia de consumidores externos o dinámicos, ni permite certificar la seguridad de eliminar tablas, credenciales, migraciones o archivos de configuración usados durante un rollback. Tampoco sustituye telemetría de producción ni pruebas funcionales con GBP/Tiendanube.

## 2. Hallazgos y disposiciones de limpieza

| ID | Evidencia | Disposición | Justificación |
|---|---|---|---|
| G-01 | `features/confirmations.js` se importaba e inicializaba, pero ningún template ni otro módulo consume `data-confirm`. | **ELIMINAR** | Código de interfaz sin consumidor; se retiraron importación y llamada de inicialización. |
| G-02 | `product_audit_interval_hours` solo figuraba en configuración y `.env.example`, sin lector de comportamiento. | **ELIMINAR opción** | Evita parámetro operativo que no tiene efecto real. |
| G-03 | `.env.example` definía dos veces `ONLINE_PRICE_LIST_ID` y `ECOMMERCE_STORAGE_IDS`, con valores distintos. | **UNIFICAR** | Fuente única para el ejemplo de configuración. |
| G-04 | `.env.example` incluía `GBP_DIAGNOSTIC_*` sin consumidores en el código analizado. | **ELIMINAR ejemplos** | No son parámetros reconocidos por `ConfiguracionAplicacion`. |
| G-05 | Un importador periódico está anunciado por `IMPORT_SCHEDULER_ENABLED` pero el scheduler solamente registra una advertencia y no crea jobs de importación. | **MANTENER flag por compatibilidad y etiquetar claramente «No disponible»** | Suprimir el flag podría ignorar silenciosamente una variable existente; la implementación no se debe simular. Requiere ADR si se decide retirar contrato o implementar realmente la funcionalidad. |
| G-06 | `render.yaml` y `Procfile` pertenecen al proceso de despliegue anterior. | **ELIMINACIÓN DIFERIDA** | Mantener solo mientras Render siga operativo como rollback; eliminar tras el corte. |
| G-07 | ZIP de origen incluye `.env` y bases locales `.db`. | **NO incluir en parche. Revisar control de versiones y secretos.** | Los datos y credenciales no son garbage eliminable ciegamente. Rotar credenciales expuestas y retirar secretos del control de versiones (incluido historial si corresponde). |
| G-08 | `runtime.txt` puede influir en un buildpack o despliegue heredado. | **RETENER** | No hay evidencia suficiente para darlo de baja antes de validar Railway. |
| G-09 | Fachada `trabajos_masivos.py`, históricos, scripts, SQL y archivos `__init__.py`. | **RETENER** | Hay contratos de compatibilidad, pruebas, posibles clientes externos, documentación o importación de paquetes. |
| G-10 | `StockScheduler = IntegradorScheduler` solo aparece en el scheduler. | **RETENER provisionalmente** | Alias histórico explícito; no se puede excluir consumidores externos sin inventario de despliegues y automatizaciones. |

**Conclusión:** un único archivo puede borrarse ahora con prueba estática suficiente; se ejecutaron además limpiezas puntuales de opciones y configuración. El resto no se elimina basándose en nombres, tamaño, antigüedad o heurísticas frágiles.

## 3. Problemas UX observados y modificaciones

| Componente | Problema identificado | Mejora implementada |
|---|---|---|
| Navegación general | Menú lateral poco descriptivo; experiencia móvil sin overlay ni contención de foco | Nueva estructura, semántica de navegación, indicador de sección, panel móvil con backdrop y cierre con Escape, restauración de foco y acceso «Saltar al contenido». |
| Diseño visual | CSS minimizado y parcialmente acumulativo; dependencia de Google Fonts | Design system reescrito por áreas con variables de tema, tipografía local del sistema, espaciado, estados, superficies y breakpoints; sin dependencia de fuentes de terceros. |
| Accesibilidad | Feedback e interacciones difíciles de operar solo con teclado | Semántica y labels, `aria-current`, `aria-expanded`, encabezados, controles con foco visible, soporte `prefers-reduced-motion` y `aria-live` para estados. |
| Preferencias | Sin opción visual de tema | Modo claro/oscuro, preferencia del sistema y conservación local de la selección; sin dependencias adicionales. |
| Centro de trabajos | No permitía inspección detallada del job; estados técnicos poco legibles | Resumen de los ocho estados, filtros por estado/búsqueda, modal de inspección, mensajes, códigos de error, intentos, worker, heartbeat, fechas y contadores. |
| Seguimiento | El indicador «En vivo» no explicaba el muestreo ni los errores de conexión | Indica actualización y cantidad de jobs activos; estado desconectado explícito y reintentos controlados. Se conserva polling 2 s activo/60 s inactivo/15 s fallos y pausa por pestaña oculta. |
| Tareas iniciadas | El usuario no llegaba al job recién encolado | Navegación a `?focus=<job_id>` y apertura del detalle después de recibirlo. |
| Tabla de jobs | En móvil exigía desplazamiento horizontal incluso para el resumen | Presentación de cada job reciente como tarjeta accesible en móvil. |
| Auditoría | Solo se exponía el último evento | Historial acotado de 50 eventos ordenados por PK descendente: se reutiliza el índice ya existente y se evita introducir migraciones. |
| Productos | La búsqueda era solo del lote visible, sin explicitarlo | Contador de resultados local, estado vacío específico y texto claro de límite de búsqueda. No se promete búsqueda global. |
| Estado de servicios | Se interpretaba la configuración del scheduler como evidencia de ejecución | Diferenciación «habilitada/deshabilitada» de «funcionando» y descripción del alcance del indicador. |
| Configuración | Se mostraba «Configurado / Activo» incluso para flags booleanos | Valores semánticos «Sí/No» y aviso de que la vista no valida terceros. |
| Dashboard | La distribución sin decisiones quedaba completamente vacía | Estado vacío explicativo. |

**No se agregaron endpoints comerciales de escritura, sockets, Redis, Celery ni bibliotecas UI.** Se reutilizaron rutas y contratos de jobs existentes. La única incorporación de consulta al backend es `listar_recientes(limit=50)` en el repositorio de auditoría.

## 4. Integridad del dominio y delimitaciones

Se conservaron los procesos y los contratos GBP/Tiendanube: exportaciones 12/13/14, productos, stock, precios, clientes, pedidos, webhooks y reglas de precio cero frente a fila ausente. No se efectuaron cambios de esquema ni migraciones adicionales. El frontend **no reintenta** automáticamente jobs `REQUIERE_REVISION`; indica la conciliación manual requerida.

Para el historial de auditoría, un límite fijo de 50 evita consultas y transferencias no acotadas. La ordenación por PK descendente aprovecha el índice primario y representa el orden de registro, no necesariamente el orden temporal de finalización de operaciones concurrentes.

## 5. Pruebas ejecutadas

| Validación | Resultado |
|---|---|
| Suite Python completa | **130 passed**, 0 fallos, 0 warnings en ejecución final |
| Suite anterior | 117 passed, referencia antes de cambios UX |
| Compilación Python | `python -m compileall -q app tests` sin errores |
| Chequeo de sintaxis JS | `node --check` sobre todos los módulos sin errores |
| Parser CSS | `tinycss2`, sin errores de sintaxis de nivel de hoja |
| Renderizado HTML | Las 10 páginas del panel respondieron HTTP 200 usando SQLite aislado |
| Visual estático | 1440 px y 390 px; sin scroll horizontal del documento (tablas grandes poseen scroll local) |
| Pruebas UI interactivas aisladas | Tema, menú móvil, filtros, detalle de job y cierre de modal ejecutados en Chromium; sin errores JS |
| Integraciones externas reales | **No ejecutadas** |
| PostgreSQL de Railway | **No conectado ni alterado** |
| Benchmarks LCP, CLS, TTI, p95 | **No realizados** |
| Ruff CLI | **No disponible en este contenedor**; no se declara aprobado |

**Importante:** la validación de navegador es aislada y utiliza respuestas simuladas para jobs; no equivale a pruebas integradas sobre un Railway desplegado. La prueba de renderizado no valida todas las combinaciones de permisos, miles de registros o comportamiento en dispositivos reales.

## 6. Performance: efectos y trade-offs

- Se eliminó la solicitud externa a Google Fonts, reduciendo dependencia de terceros. El tamaño final de CSS aumenta respecto de la hoja anterior: se privilegió legibilidad, funcionalidad responsive y estados accesibles. No se afirma una mejora porcentual sin mediciones.
- El polling adaptativo se conserva, sin SSE ni colas adicionales. La pausa cuando la pestaña está oculta continúa activa.
- La consulta de auditoría no expone un listado ilimitado y utiliza índice de PK; debe verificarse latencia real si el historial crece significativamente.
- El filtrado de historial de jobs permanece sobre los últimos 100 registros cargados; el filtrado de productos es local a la página actual. Estos límites se informan al operador en la interfaz.

## 7. Archivos y política de aplicación

El ZIP incremental se construye **contra la versión anterior ya refactorizada**, no contra el ZIP original. Contiene únicamente los archivos nuevos y modificados con sus rutas relativas. **No incluye** `.env`, bases SQLite, caches, binarios compilados ni una copia completa del proyecto.

### Eliminación explícita posterior a aplicar el ZIP

```text
app/static/enterprise/features/confirmations.js
```

Usar el manifiesto SHA-256 entregado por separado antes de borrarlo, para evitar eliminar una versión modificada con nuevos consumidores. Eliminar también su rastro en Git cuando corresponda. No se eliminarán automáticamente otros archivos.

### Archivos diferidos para el corte de Railway

- `render.yaml` y `Procfile`: confirmar que no son necesarios para rollback ni otros consumidores.
- `.env`: conservar copia local segura si corresponde, sacarlo de Git y no enviarlo en el despliegue. Rotar secretos si fueron expuestos.
- `integrador_gbp_tn.db` y `integrador_pruebas.db`: verificar si contienen datos únicos o registros de prueba antes de moverlos fuera de un repositorio; nunca convertirlos en un borrado de producción.
- `runtime.txt`: decidir cuando esté verificado el buildpack definitivo.
- Fuentes históricas, scripts y fachada de compatibilidad: conservar hasta demostrar falta de consumidores y aprobar una deprecación.

## 8. Instalación y rollback

1. Mantener backup o commit limpio y aplicar **primero** el ZIP de refactorización Railway aprobado si aún no se integró.
2. Aplicar el ZIP UX/UI sobre esa misma raíz, sin copiar bases `.db` ni `.env`.
3. Comparar el hash del archivo obsoleto con el manifiesto; borrarlo en una operación explícita de Git o del explorador de archivos.
4. Ejecutar `python -m pytest -q`, `python -m compileall -q app tests` y `node --check` sobre módulos JS. Validar la configuración de entorno local.
5. Validar manualmente en pantallas grandes y pequeñas, y con teclado: menú, tema, jobs activos, seguimiento, cancelación, estado `REQUIERE_REVISION`, auditoría, productos, navegación y formularios.
6. Solo tras certificar la migración previa (schema, backup, env, API/worker/scheduler) desplegar a Railway; comprobar los webhooks y trabajos reales.
7. Para rollback de esta interfaz, restaurar únicamente los archivos cambiados y la configuración anterior, reincorporando `confirmations.js` si se revierte también la eliminación. La actualización UX/UI no requiere downgrade de base de datos.

## 9. Riesgos abiertos y decisiones pendientes

| Severidad | Riesgo/limitación | Criterio de cierre |
|---|---|---|
| Alta | Instalación de la refactorización de infraestructura anterior aún no validada en Railway | Preflight, backup+restore, migraciones en copia, validación funcional de workers/webhooks |
| Alta | Secretos presentes en el ZIP original | Inventario de secretos, exclusión de repositorio y rotación si corresponde |
| Media | Accesibilidad WCAG integral no auditada | Revisión con lector de pantalla y pruebas de teclado en dispositivo real |
| Media | Búsqueda global de productos no implementada | Definir consulta indexada y paginación servidor si hay requerimiento operativo |
| Media | Historial de auditoría limitado a últimos 50 | Definir búsqueda histórica paginada y políticas de retención según volumen |
| Media | Performance real de navegador/CPU/RAM no medida | Medición antes/después en Railway con volúmenes representativos |
| Media | `IMPORT_SCHEDULER_ENABLED` no tiene workload implementado | ADR para implementar auditoría planificada o retirarlo formalmente, verificando consumidores |
| Baja | Artefactos Render presentes para rollback | Eliminarlos únicamente después del corte y período de observación |

## 10. Decisión de salida

**GO para integrar localmente la actualización UX/UI y continuar con QA en staging. NO-GO para despliegue productivo directo**, dado que el corte Railway y las validaciones end-to-end del parche previo no están acreditados.

La limpieza es deliberadamente **conservadora y verificable**. «Eliminar cualquier cosa que no sirva» no autoriza borrar archivos con consumidores externos desconocidos ni datos sin inventario y respaldo.
