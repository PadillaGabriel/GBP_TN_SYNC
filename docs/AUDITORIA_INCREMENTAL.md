# Auditoría incremental de productos GBP

Se agregó una auditoría incremental para avanzar por tandas sin reprocesar siempre desde el inicio del catálogo.

## Endpoint JSON

```http
POST /sync/audit/productos/next?limit=200&concurrency=3
```

Reglas:

- Consulta el catálogo básico de GBP.
- Filtra candidatos con imagen Website.
- Excluye SKUs ya auditados en `productos_fuente`.
- Procesa solo los próximos `limit` candidatos pendientes.
- Guarda producto, validación, stock y auditoría.
- No crea ni actualiza productos en Tienda Nube.

La respuesta incluye:

```json
{
  "modo_incremental": true,
  "candidatos_con_imagen_website": 3694,
  "candidatos_ya_auditados": 200,
  "candidatos_pendientes_auditar": 3494,
  "procesados": 200,
  "publicables": 0,
  "bloqueados": 0
}
```

## Panel visual

Se agregaron acciones al panel:

- `Auditar próximos 50`
- `Auditar próximos 200`
- `Importar pendientes 25`
- `Importar pendientes 50`

URL:

```text
/admin/panel
```

## Flujo operativo

1. Auditar próximos 200.
2. Revisar publicables pendientes.
3. Importar pendientes 25 o 50.
4. Revisar Tienda Nube.
5. Repetir.
