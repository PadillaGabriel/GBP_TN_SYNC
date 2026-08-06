# Integrador GBP ↔ Tiendanube

Microservicio único para Silmar Bazar que integra GBP y Tiendanube.

## Subsistemas

1. Sincronización de stock GBP → Tiendanube.
2. Importación, auditoría y gestión de productos.
3. Panel administrativo de decisiones y trabajos masivos.
4. Clientes y pedidos Tiendanube → GBP mediante Web Services nativos.

## Seguridad operativa de pedidos

La escritura temporal y la confirmación final se controlan de manera independiente:

```env
DRY_RUN=false
PEDIDOS_ESCRITURA_GBP_HABILITADA=true
PEDIDOS_GBP_STAGING_ENABLED=true
PEDIDOS_GBP_CONFIRMATION_ENABLED=false
PEDIDOS_GBP_TOTAL_TOLERANCE=0.01
PEDIDOS_GBP_RESIDUAL_MAXIMO_AJUSTABLE=0.05
```

Mantener `PEDIDOS_GBP_CONFIRMATION_ENABLED=false` hasta realizar la prueba final controlada.

## Ejecución local

```powershell
python -m pytest -q
python -m compileall app tests
python -m uvicorn app.principal:app --host 127.0.0.1 --port 8000
```

Panel: `http://127.0.0.1:8000/admin`

Swagger: `http://127.0.0.1:8000/docs`
