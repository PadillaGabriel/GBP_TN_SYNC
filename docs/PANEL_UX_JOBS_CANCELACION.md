# Panel UX, jobs recuperables y cancelación

## Objetivo

El panel administrativo no debe depender de logs de Render para saber si una acción está trabajando.
Las operaciones largas se ejecutan como jobs persistidos y se consultan desde el panel.

## Cambios

- Se eliminó el aviso visual grande de `DRY_RUN=false` del panel.
- El bloque de procesos deja de usar fondo blanco y queda integrado al diseño oscuro.
- El botón **Actualizar** de procesos refresca la lista y abre el primer proceso activo si existe.
- El popup de progreso muestra métricas resumidas, barra, porcentaje y detalle técnico opcional.
- Se agrega botón **Cancelar proceso**.
- La cancelación se guarda como `CANCELACION_SOLICITADA` y el proceso se detiene en el siguiente punto seguro.
- Los procesos terminales pueden quedar como `FINALIZADO`, `FINALIZADO_CON_ERRORES`, `ERROR` o `CANCELADO`.

## Alcance de cancelación

La cancelación no interrumpe una llamada externa ya iniciada contra GBP o Tienda Nube. El job se detiene entre tandas o entre productos.

## Endpoints

```http
GET  /admin/panel/jobs
GET  /admin/panel/jobs/{job_id}
POST /admin/panel/jobs/{job_id}/cancel
```

## Operaciones convertidas a job visible

- Reconciliar TN
- Reset mapeos locales
- Normalizar categorías
- Auditar próximos
- Auditar todo
- Importar pendientes
- Importar todo
- Importar SKU
- Sync stock lote
- Sync stock SKU
- Reauditorías por bloqueo

## Seguridad operativa

La importación total ahora corta si detecta falta de avance en una tanda para evitar quedar en ejecución indefinida cuando todos los seleccionados fallan.
