# Etapa 7 — Microservicio integrado final

## Alcance conservado

La entrega mantiene dentro de una única aplicación FastAPI los subsistemas productivos existentes:

- sincronización de stock GBP → Tiendanube;
- importación, auditoría y administración de productos GBP → Tiendanube;
- panel administrativo de decisiones y trabajos masivos;
- recepción idempotente de pedidos Tiendanube;
- resolución o creación controlada de clientes GBP;
- preparación, staging, conciliación y confirmación de pedidos GBP.

## Endurecimiento final de pedidos

- La confirmación reutiliza el mismo flujo de staging validado en la Etapa 6.
- Siempre genera un GUID nuevo antes de confirmar; no reutiliza buffers potencialmente vencidos.
- Conserva la expansión nativa de artículos asociados realizada por GBP.
- Conserva la conciliación residual controlada sobre CUPON.
- Bloquea la confirmación si el staging final no concilia.
- Reserva atómicamente cada confirmación para evitar ejecuciones concurrentes.
- Una segunda llamada sobre un pedido confirmado responde de forma idempotente sin escribir nuevamente.
- Persiste `soh_id` y el GUID final usado por GBP.
- Registra el error de confirmación y libera el pedido para una reejecución controlada.
- La confirmación sigue protegida por `PEDIDOS_GBP_CONFIRMATION_ENABLED`.

## Evolución de base de datos

El arranque incorpora una migración mínima, explícita y compatible para instalaciones existentes. Solo agrega, cuando faltan:

- `pedidos_externos.gbp_guid`;
- `pedidos_externos.confirmation_error`.

No recrea tablas ni elimina información.

## Limpieza

- No se incorporó SQL directo contra GBP.
- No se reintrodujeron GBPScripts ni validadores históricos.
- No se duplicó la carga temporal dentro de la confirmación.
- Se eliminaron informes de etapas anteriores, cachés y bytecode.
- El ZIP no contiene `.env`, bases locales, credenciales ni entornos virtuales.

## Validación

- `83 passed` con pytest.
- `compileall` correcto para `app` y `tests`.
