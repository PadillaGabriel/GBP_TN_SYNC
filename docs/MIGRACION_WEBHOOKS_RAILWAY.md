# Migración de eventos de pedidos Tiendanube a Railway

## Qué hace el parche
- Recibe **10** eventos conocidos `order/*` en `/pedidos/webhooks/tienda-nube`.
- Valida HMAC contra secreto principal o `TIENDA_NUBE_WEBHOOK_SECRET_LEGACY` si los eventos proceden de una segunda aplicación.
- Exige el `store_id` correspondiente.
- Persiste primero un job en `sync_jobs` (HTTP 202 solo después de commit); cada evento está deduplicado por su ID, evento y timestamp o cuerpo. `order/paid` mantiene una sola clave por orden.
- En el worker, los eventos no pagados crean un registro de pedido local si falta y agregan historial; **no escriben en GBP**.
- Solo `order/paid` ejecuta cliente/pedido GBP, y verifica `payment_status == paid` y orden no cancelada antes de escribir.
- Una cancelación sobre un pedido GBP ya confirmado produce un job `REQUIERE_REVISION`: no cancela automáticamente el pedido ERP.

## Límites importantes
- El webhook `order/updated` también se entrega junto con eventos específicos. El job registra cada evento y consulta el estado ACTUAL de la orden (no asume orden de llegada).
- El repositorio de pedidos existente es idempotente: no reescribe una orden previamente recibida. Las modificaciones financieras posteriores al pago requieren revisión/conciliación; **no se sincronizan automáticamente a GBP**.
- Si un `order/paid` se procesa una vez y luego la orden cambia nuevamente a pagada, la clave del job existente requiere conciliación; no reiniciar sin verificar efectos externos.
- Los pedidos pagados durante la caída de Render necesitan conciliación separada; actualizar URL no los reenvía necesariamente.
- El sistema no integra `product/*`, `customer/*`, `app/*` o webhooks de privacidad; este cambio cubre los 10 eventos de pedidos identificados.

## Despliegue
1. Aplicar parche sobre la versión actual de GitHub **comparando diferencias**; no reemplazar ramas o credenciales. Realizar backup y crear una rama.
2. En Railway configurar las mismas credenciales de DB y Tiendanube para WEB y WORKER. Requiere `DATABASE_URL` PostgreSQL en ambos.
3. WEB: `TIENDA_NUBE_WEBHOOK_EVENTS=order/created,order/updated,order/paid,order/packed,order/fulfilled,order/cancelled,order/edited,order/pending,order/voided,order/unpacked`.
4. Si los webhooks antiguos pertenecen a otra aplicación Tiendanube, configurar `TIENDA_NUBE_WEBHOOK_SECRET_LEGACY` al `client_secret` de esa aplicación, sin compartirlo ni usar su access token como secreto.
5. Mantener `TIENDA_NUBE_PEDIDOS_AUTOMATICOS_HABILITADOS=true`; solo habilitar las escrituras GBP tras validar `DRY_RUN=false`, staging y confirmación, y los mapeos de negocio.
6. Desplegar **WEB + WORKER**. Verificar 202 + job + `job_claimed` para un evento de prueba controlado. Verificar HMAC en ambas apps antes de migrar.
7. Ejecutar la vista previa del script de migración en PowerShell: `./scripts/migrar_webhooks_railway.ps1 -IncludeLegacy`.
8. Si la lista corresponde a los 11 webhooks que compartiste, ejecutar `./scripts/migrar_webhooks_railway.ps1 -IncludeLegacy -Apply`.
9. Revisar la página Performance en Partners y los logs de Railway. Comprobar funcionamiento por cada tipo de evento.
10. Para revertir, restaurar las URLs por ID (guardar la salida inicial del script y exportar la lista de webhooks), sin modificar ID/event.

## Seguridad
- **No ejecutar el script antes de tener el backend desplegado** o todos los eventos antiguos terminarán fallando.
- No desactivar HMAC ni permitir una lista arbitraria de eventos.
- No loguear cuerpos completos de pedidos ni tokens; contienen datos personales.
- Cualquier payload inválido, orden sin SKU, pago no confirmado o incertidumbre tras una escritura GBP lleva a revisión, no a una venta ciega.

## Verificación de trabajo existente (solo lectura)
```sql
SELECT id, tipo, estado, idempotency_key, created_at, error_codigo, error_detalle
FROM sync_jobs
WHERE idempotency_key LIKE '%2125893909%'
ORDER BY id DESC;
```

## Pruebas
`python -m pytest -q`
