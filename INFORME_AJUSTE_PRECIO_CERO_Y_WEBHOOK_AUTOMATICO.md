# Ajuste de decisión de precio cero y validación del orquestador automático

## Regla de precio

- Fila presente en exportación 13 con `precio_final = 0`: `PUBLICABLE_CONSULTAR_PRECIO`.
- Fila ausente en exportación 13: `NO_PUBLICAR_PRECIO_NO_ENCONTRADO`.
- Precio negativo: `NO_PUBLICAR_PRECIO_NEGATIVO`.
- Stock cero consultable: permitido y enviado como cero.

## Webhook automático

Ruta: `POST /pedidos/webhooks/tienda-nube`.

Flujo validado por pruebas:

1. valida firma HMAC;
2. valida `store_id`;
3. valida evento configurado;
4. verifica `TIENDA_NUBE_PEDIDOS_AUTOMATICOS_HABILITADOS`;
5. encola `_procesar_pedido_tienda_nube_en_segundo_plano(order_id)`;
6. abre una sesión independiente;
7. construye `ProcesarPedidoTiendaNube`;
8. ejecuta importación de orden, cliente GBP y confirmación del pedido.

## Prueba real recomendada

Configurar en `.env`:

```env
TIENDA_NUBE_WEBHOOK_SECRET=<secreto real>
TIENDA_NUBE_WEBHOOK_EVENTS=order/paid
TIENDA_NUBE_PEDIDOS_AUTOMATICOS_HABILITADOS=true
```

El webhook productivo debe apuntar a:

```text
https://<host>/pedidos/webhooks/tienda-nube
```

Crear una orden de prueba pagada y comprobar en Pedidos, Trabajos, Auditoría y GBP que el procesamiento se realizó sin intervención manual. Repetir el mismo evento y confirmar idempotencia.
