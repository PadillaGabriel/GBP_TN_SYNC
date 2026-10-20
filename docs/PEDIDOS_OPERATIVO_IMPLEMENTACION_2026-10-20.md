# Pedidos Tiendanube → GBP — módulo operativo

## Alcance

- Página `/admin/panel/pedidos`: recepción manual y procesamiento completo **separados**, indicadores, historial paginado, filtros, detalle modal.
- `GET /pedidos/operaciones/historial`: devuelve `total`, `items`, `ultimo_confirmado`, `limit` y `offset`. Busca por ID de orden TN, número de orden o pedido GBP. La búsqueda nunca expone información personal.
- `GET /pedidos/operaciones/{pedido_id}/detalle`: consulta de etapa, cliente GBP vinculado, artículos y eventos registrados; no devuelve datos personales ni payload crudo.
- `POST /pedidos/tienda-nube/{order_id}/procesar-gbp`: encola el **procesador existente** del worker. No ejecuta escrituras en el proceso web. Requiere en web las cuatro condiciones `PEDIDOS_ESCRITURA_GBP_HABILITADA=true`, `PEDIDOS_GBP_STAGING_ENABLED=true`, `PEDIDOS_GBP_CONFIRMATION_ENABLED=true`, `DRY_RUN=false`. El worker también deberá tener la configuración correcta.
- `POST /pedidos/tienda-nube/{order_id}/importar`: sigue siendo solo recepción local; la interfaz ahora lo explica correctamente.

## Criterios de confirmación

Solo cuenta como **confirmado en GBP** un pedido con `estado_integracion=CONFIRMADO` y `gbp_order_id` persistido. Un HTTP 202, un job `FINALIZADO`, o la recepción local no equivalen por sí solos a confirmación documental. No hay creación de tablas ni migración del esquema.

## Limitaciones y comprobación de producción

1. Validar webhook TN, secreto y eventos habilitados contra la cuenta real.
2. Validar estado del servicio worker Railway, conectividad a PostgreSQL y sus variables de entorno.
3. Comprobar con una orden de prueba real que el cliente GBP se vincula/crea, el pedido se confirma exactamente una vez y aparecen `gbp_order_id`, historial y trabajo coherentes.
4. Los cambios de estado del job se observan en Centro de trabajos; la tabla de Pedidos muestra el estado de negocio persistido. El historial solo incluye órdenes ya registradas en el integrador y **no recupera automáticamente el pasado de Tiendanube**.
5. Un trabajo manual se idempotentiza por `tn:manual:{order_id}`. Si ese job ya existe (incluido estado de error), se devuelve el mismo ID y requiere revisión manual antes de una nueva ejecución; no reintenta a ciegas.
6. La configuración visible de la vista web no garantiza por sí sola que las variables del worker coincidan.
7. La nueva interfaz no habilita escrituras automáticamente ni cambia los circuitos internos GBP.

## Comprobaciones locales

Ejecutar `pytest -q` y `node tests/test_accion_formulario_jobs.mjs`.
