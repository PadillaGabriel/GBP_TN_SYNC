# GBP_TN_SYNC — Refactorización integral hacia Railway

**Entrega técnica:** 2026-10-13 · **Estado:** código validado localmente, corte productivo pendiente · **Base:** ZIP recibido.

## 1. Alcance realmente ejecutado

1. API FastAPI sin ejecución de trabajos largos mediante `BackgroundTasks` y sin scheduler durante el ciclo de vida HTTP.
2. Worker separado (`app.procesos.worker`) con cola PostgreSQL, adquisición exclusiva por `FOR UPDATE SKIP LOCKED`, heartbeat y lease.
3. Scheduler separado (`app.procesos.programador`) que **encola** sincronizaciones con idempotencia por intervalo, sin ejecutarlas en la API.
4. Webhooks Tiendanube: HMAC y comprobación de tienda conservadas; job durable e idempotente antes de responder 202.
5. Progreso, payload, errores e identidad del worker separados en `sync_jobs`, con lectura de estados legados y cuarentena de ejecuciones vencidas.
6. Máquina de transiciones validada para evitar saltos ilegales y resurrección de jobs terminales.
7. Módulo masivo segregado en auditoría, importación, stock, categorías, reconciliación y funciones comunes; fachada de compatibilidad sin replicar lógica.
8. Auditoría GBP con ventanas acotadas de tareas asíncronas; mantiene la misma concurrencia máxima solicitada y el procesamiento existente.
9. Panel de jobs: estado `REQUIERE_REVISION`, mensajes separados, estado de worker, heartbeat y timestamps disponibles por API, sin nuevas dependencias de frontend.
10. Alembic con baseline `0001` y expansión `0002` (índice de claim, índice único de idempotencia, payload/progreso, heartbeat, ownership y fechas).
11. Protección de las rutas administrativas y manuales en producción por Basic Auth HTTPS; el webhook HMAC permanece exceptuado.
12. Tres archivos de arranque Railway y `preflight_railway.py` de inspección **read-only**.

**No se realizaron modificaciones en las reglas comerciales**: exportaciones GBP 12/13/14, productos, políticas de publicación para precio 0, diferencias con fila de precio ausente, clientes y confirmaciones de pedidos conservan su código y flags de seguridad.

## 2. Evidencia y resultados

- Base recibida: `110 passed` antes de cambiar el código.
- Refactorización: `117 passed` y 0 fallas en suite actual.
- `python -m compileall -q app tests`: aprobado.
- `alembic upgrade head`: aprobado en SQLite aislado nuevo.
- `alembic downgrade 0001`: aprobado en SQLite de prueba.
- `alembic check`: sin diferencias de metadata sobre SQLite migrado.
- API local: `/health` y `/openapi.json` HTTP 200.
- Pruebas nuevas de idempotencia, claims exclusivos, cancelación, cuarentena por lease, separación del error/progreso, seguridad administrativa y dispatch de parámetros.

**No equivalen a certificación productiva:** no se ha conectado a PostgreSQL de Railway ni se han ejecutado benchmarks reales, restauración de backups, auditorías de proveedores ni pruebas de concurrencia con varios procesos PostgreSQL. En el entorno de análisis no se encuentra instalado `psycopg`, aunque está fijado en `requirements.txt`; la vista SQL offline para PostgreSQL no pudo generarse.

## 3. Decisiones consolidadas

- **ADR-001:** consolidación Railway (aprobada por usuario).
- **ADR-002:** separar plano de control HTTP y ejecución de trabajos.
- **ADR-003:** PostgreSQL como cola durable, sin Redis/Celery de entrada.
- **ADR-004:** scheduler separado, con deduplicación transaccional por ventana.
- **ADR-005:** estados explícitos, progreso y errores desacoplados, lease y cuarentena.
- **ADR-006:** migración versionada con Alembic, sin cambios de tablas en startup.
- **ADR-007:** mantener polling adaptativo; SSE no justificado sin métricas.
- **ADR-008:** limpieza conservadora de código funcional; eliminar código vacío y segmentar archivo grande.
- **ADR-009:** corte con backup/restauración comprobados y rollback sin modificar producción inadvertidamente.

## 4. Riesgos y limitaciones abiertos

| Riesgo / limitación | Severidad | Condición de resolución |
|---|---|---|
| Estado real del esquema PostgreSQL productivo desconocido | Crítica | Preflight, backup y migración de copia restaurada |
| Un pedido confirmado remotamente puede fallar antes del ACK local | Crítica | Conciliación comercial en `REQUIERE_REVISION`; nunca auto-retry ciego |
| No se ha certificado paralelismo de varios workers contra los mismos SKUs | Alta | Empezar con 1 worker y probar locks por recurso antes de escalar réplicas |
| Batch parcial interrumpido no se reanuda automáticamente por ítem | Alta | Reconciliar efectos y ejecutar nuevo job supervisado; posible siguiente ADR para checkpoints finos |
| Falta prueba de firma/webhook en URL definitiva | Alta | Validación HMAC en Railway con webhook de prueba real |
| API heredada pudo tener clientes automatizados sin Basic Auth | Media/Alta | Actualizar consumidores y configurar secrets antes del corte |
| No hay benchmark p50/p95, uso RAM ni costo facturado Railway | Media | Medir con catálogo real, sin prometer ahorro porcentual |
| El motor HTTP SOAP GBP puede seguir usando HTTP según configuración legada | Alta | Validar con proveedor disponibilidad HTTPS, no cambiar sin compatibilidad |
| Secretos incluidos en el ZIP original | Alta | Rotar credenciales expuestas y excluir `.env` del repo y de artefactos |
| Historial de ejecución por sublote y dashboard detallado de workers no implementado | Media | Validar si consumo/operación justifican tabla extra o panel especializado |

## 5. Operación y criterios GO / NO-GO

**NO-GO productivo hasta completar:**

1. Backup PostgreSQL y restore en base aislada, con integridad y tiempos constatados.
2. Preflight de schema + `alembic stamp 0001` solo si schema existente coincide; `alembic upgrade head` probado en copia restaurada.
3. Configurar Railway WEB+WORKER y SCHEDULER solo si se habilitarán tareas recurrentes. Un worker inicial; `DATABASE_URL` referenciado a PostgreSQL existente, `APP_ENV=production`, secrets admin, TN y GBP.
4. Probar todos los contratos GBP y Tiendanube, particularmente precio cero/ausencia de exportación 13, orden de pedidos, HMAC, reenvío duplicado y autorización del panel.
5. Pruebas de kill/restart, expiración de lease, cancelación concurrente y validación PostgreSQL multi-proceso.
6. Benchmark representativo y medición de factura Railway; aceptar umbrales antes de escalar.
7. Actualizar URL de webhook, observar pedidos reales supervisados; no activar confirmaciones GBP por mera migración.
8. Desactivar Render solo tras pruebas satisfactorias; conservar capacidad de rollback durante el período acordado.

**Rollback de aplicación:** detener scheduler/worker nuevos y revertir la versión binaria; conservar columnas adicionales de la migración `0002` (*expand-only*, la versión anterior puede ignorarlas). No ejecutar `alembic downgrade` sobre PostgreSQL productivo sin estrategia de reversión de datos: el downgrade elimina columnas operativas. Si hubiera corrupción, restaurar únicamente el backup validado con un RPO/RTO acordado.

## 6. Higiene de artefactos

El parche incremental **no contiene** `.env`, bases SQLite, caches, binarios Python ni archivos de historial no modificados. El archivo `render.yaml` y el `Procfile` antiguo pueden eliminarse de la rama principal **después del corte** y cuando ya no tengan consumidores; no se eliminan ahora para permitir rollback. Los demás archivos conservan funcionalidad o contratos observables, por lo que no se borran por su nombre.

## 7. Nota sobre "definitiva"

Se entrega **una única rama/parche cohesivo para validación**, no un despliegue realizado ni evidencia de operación end-to-end en Railway. La diferencia es técnica y obligatoria: sin PostgreSQL real, backups verificados, acceso a Railway ni credenciales externas no es posible garantizar integridad ni rendimiento productivo. El documento identifica expresamente los controles pendientes de aprobar antes del GO.
