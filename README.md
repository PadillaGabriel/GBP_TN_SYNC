# GBP_TN_SYNC — Integrador Global Blue Point ↔ Tiendanube

Servicio FastAPI con sincronización de artículos, stock, precios, clientes y pedidos.
La lógica comercial de integración no se modifica con la infraestructura de jobs.

## Despliegue objetivo: Railway

- **WEB**: `uvicorn app.principal:app --host 0.0.0.0 --port $PORT` — API y panel, sin scheduler ni jobs en `BackgroundTasks`.
- **WORKER**: `python -m app.procesos.worker` — consume solicitudes durables; inicialmente **1 instancia** hasta verificar los límites externos y paralelismo cruzado.
- **SCHEDULER**: `python -m app.procesos.programador` — genera solicitudes idempotentes de stock, inicialmente **1 instancia**; desplegarlo solo si `STOCK_SCHEDULER_ENABLED=true`.
- **PostgreSQL**: conservar la base actual de Railway, con backups probados antes de migrar.

Los archivos `railway.*.toml` contienen la configuración de arranque para cada servicio. Configurar la ruta correspondiente al crear los servicios en Railway. La API requiere un dominio público HTTPS; el worker y scheduler **no**.

## Primera instalación y upgrade seguro

Las migraciones no se aplican al iniciar FastAPI. `alembic upgrade head` es una operación explícita y auditada.

En una base **vacía**, luego de configurar `DATABASE_URL`, ejecutar `alembic upgrade head`.

En la base **existente** de Railway, antes de habilitar cualquiera de los tres servicios:

1. Detener jobs y scheduler de Render; mantener los webhooks apuntando al origen hasta completar el corte controlado.
2. Hacer backup consistente de PostgreSQL; efectuar una **restauración de prueba** en una base aislada y registrar tiempos, tamaño y comprobaciones.
3. Ejecutar `python -m scripts.preflight_railway`; conciliar cualquier job de estado ambiguo, sin reintento ciego.
4. Verificar manualmente tablas y columnas del esquema legado frente a `migrations/versions/0001_baseline_existing_schema.py`. Si no existe `alembic_version` y se confirma equivalencia, ejecutar `alembic stamp 0001` **una vez**.
5. Ejecutar `alembic upgrade head` primero en la **copia restaurada** y comprobar los datos. Repetir en producción solo después de la aprobación del corte.
6. Arrancar WEB, WORKER y SCHEDULER en Railway con variables de entorno compartidas por referencia a Railway PostgreSQL y secretos exclusivos de servicio.
7. Validar API, panel, stock, auditoría, recepción HMAC de webhook y estado de jobs. Mantener confirmación GBP deshabilitada hasta la prueba supervisada.
8. Actualizar la URL del webhook de Tiendanube a Railway HTTPS; comprobar firma, idempotencia y pedido de prueba. Retirar Render solamente después de superar las pruebas.

**ATENCIÓN:** `alembic stamp` no crea tablas ni cambia columnas; marca una versión preexistente. Nunca ejecutarlo a ciegas sobre una base desconocida. Los archivos `*.db` y `.env` originales no se incluyen en el paquete incremental.

## Operación

Estados: `PENDIENTE`, `EN_PROCESO`, `CANCELACION_SOLICITADA`, `FINALIZADO`, `FINALIZADO_CON_ERRORES`, `ERROR`, `CANCELADO`, `REQUIERE_REVISION`.

`REQUIERE_REVISION` es una **cuarentena de efectos externos ambiguos**, no un error reintentable automáticamente. Corroborar pedidos/clientes/productos en los dos sistemas y registrar conciliación antes de crear una nueva solicitud. Los límites por servicio se parametrizan en su operación original; el worker procesa un job a la vez por réplica. El scheduler controla la deduplicación de cada ventana temporal usando PostgreSQL.

El panel usa polling adaptativo, desactivado cuando la pestaña no está visible. En producción, todas las rutas administrativas y manuales requieren `ADMIN_USERNAME` y `ADMIN_PASSWORD` configurados en Railway (HTTP Basic por HTTPS). El webhook Tiendanube se autentica mediante HMAC de cuerpo y `store_id`, no por usuario administrador.

Variables importantes: `DATABASE_URL`, `APP_ENV=production`, `APP_PUBLIC_BASE_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `WORKER_LEASE_SECONDS=120`, `WORKER_HEARTBEAT_SECONDS=20`, `WORKER_POLL_SECONDS=2`, `STOCK_SCHEDULER_ENABLED`, `TIENDA_NUBE_WEBHOOK_SECRET`. Consultar `.env.example` para el resto. Mantener `PEDIDOS_GBP_CONFIRMATION_ENABLED=false` hasta la prueba final controlada.

## Verificaciones locales

```bash
python -m pytest -q
python -m compileall -q app tests
# Para un ambiente local aislado de prueba:
DATABASE_URL=sqlite:///./prueba_vacia.db alembic upgrade head
```

Este parche **no** despliega Railway ni prueba los servicios externos de producción. Las restricciones de integridad requieren pruebas con la base real antes del GO productivo.
