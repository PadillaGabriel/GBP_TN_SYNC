# Reinicio de importación después de borrar publicaciones en Tienda Nube

Cuando se eliminan productos manualmente desde Tienda Nube, la base local conserva los mapeos `productos_tienda_nube` por auditoría. Si esos mapeos quedan como `activo`, el panel puede mostrar productos como importados y el importador automático no los vuelve a seleccionar.

## Estados de mapeo

- `activo`: publicación considerada vigente en Tienda Nube.
- `activo_manual`: publicación vigente creada por importación manual forzada.
- `oculto_tn`: publicación despublicada desde el panel.
- `eliminado_tn`: publicación eliminada desde el panel.
- `eliminado_externo`: publicación eliminada fuera del integrador, por ejemplo directamente en Tienda Nube.

Los estados `eliminado_tn` y `eliminado_externo` no cuentan como importados activos y no bloquean una nueva importación automática.

## Acciones del panel

### Reconciliar TN

Verifica contra la API de Tienda Nube si cada `tn_product_id` local sigue existiendo.

- No crea productos.
- No elimina productos.
- No actualiza productos.
- Solo marca como `eliminado_externo` los mapeos cuyo producto ya no existe en Tienda Nube.

Endpoint JSON:

```http
POST /admin/decisiones/reconciliar-tn?limit=500
```

### Reset mapeos locales

Usar cuando se sabe que las publicaciones fueron eliminadas manualmente desde Tienda Nube y se quiere reiniciar la carga.

Marca todos los mapeos activos como `eliminado_externo`.

- No borra auditoría.
- No borra productos fuente.
- No toca Tienda Nube.
- Permite que los SKUs publicables vuelvan a quedar disponibles para importación automática.

Endpoint JSON:

```http
POST /admin/decisiones/mapeos/marcar-eliminados-externos?confirm=true
```

## Secuencia recomendada

1. Entrar al panel:

```text
/admin/panel
```

2. Ejecutar `Reset mapeos locales` si ya se eliminó todo manualmente en Tienda Nube.

3. Revisar dashboard:

```text
Mapeados TN activos = 0
Mapeos eliminados > 0
Publicables pendientes > 0
```

4. Ejecutar importación controlada.
