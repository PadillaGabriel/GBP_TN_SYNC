# Integrador GBP -> Tienda Nube

Integrador nuevo para tomar GBP como fuente canónica y publicar/sincronizar productos en Tienda Nube.

## Decisiones principales

```text
GBP es fuente canónica.
Tienda Nube es destino.
Mercado Libre no forma parte del núcleo.
Precio solo se usa en importación inicial o actualización completa manual.
Stock se sincroniza de forma frecuente.
```

## Criterio de producto publicable

Un producto solo entra a importación automática si cumple:

```text
Tiene imagen Website en ItemBasicData_funGetXMLData
item_web == true en wsItem_funGetXMLDataById
item_disabled != true
item_not4Sale != true
WebSite_Description no vacía
precio online válido
stock disponible consultable
SKU válido
título válido
```

## Stock

El stock para Tienda Nube es stock disponible, no stock general.

```text
Campo GBP usado: Stock
No usar: FS / stock físico bruto
```

Cálculo:

```text
stock_tn = max(0, suma de Stock en depósitos habilitados)
```

## Panel admin

Endpoints iniciales:

```text
GET  /health
GET  /admin/dashboard
GET  /admin/productos
GET  /admin/productos/bloqueados
GET  /admin/depositos
POST /sync/stock/run
POST /sync/audit/productos/run
```

## Deploy

Ver:

```text
docs/DEPLOY_RENDER_RAILWAY.md
```

## Variables

Copiar:

```bash
cp .env.example .env
```

En Render, configurar las variables desde el dashboard.

## Ejecutar local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Diagnóstico GBP

```bash
python scripts/diagnosticar_gbp_metodos.py
python scripts/auditar_item_web.py --source basic
python scripts/auditar_item_web.py --source detail --only-with-basic-image --concurrency 5
```
