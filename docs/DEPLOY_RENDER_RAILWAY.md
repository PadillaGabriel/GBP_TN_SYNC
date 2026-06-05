# Deploy Render + Railway

## Objetivo

Ejecutar el integrador GBP -> Tienda Nube en Render y persistir datos en PostgreSQL Railway.

## Railway

1. Crear proyecto PostgreSQL.
2. Copiar `DATABASE_URL`.
3. Usarla en Render como variable `DATABASE_URL`.
4. La app normaliza `postgresql://` a `postgresql+psycopg://` automáticamente.

## Render

Servicio web Python.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Variables críticas

```env
DATABASE_URL=
GBP_USERNAME=
GBP_PASSWORD=
GBP_COMPANY_ID=
GBP_WEB_SERVICE_ID=
TIENDA_NUBE_STORE_ID=
TIENDA_NUBE_ACCESS_TOKEN=
ONLINE_PRICE_LIST_ID=1
ECOMMERCE_STORAGE_IDS=1,16
DRY_RUN=true
STOCK_SCHEDULER_ENABLED=false
IMPORT_SCHEDULER_ENABLED=false
```

## Activación segura

Primero desplegar con:

```env
DRY_RUN=true
STOCK_SCHEDULER_ENABLED=false
IMPORT_SCHEDULER_ENABLED=false
```

Después validar:

```text
/health
/admin/dashboard
/admin/productos
/admin/depositos
```

Luego cargar depósitos ecommerce y recién después habilitar stock frecuente:

```env
STOCK_SCHEDULER_ENABLED=true
```

## Regla de producción

No activar creación/actualización real de Tienda Nube hasta validar precio online, depósitos ecommerce y productos publicables.
