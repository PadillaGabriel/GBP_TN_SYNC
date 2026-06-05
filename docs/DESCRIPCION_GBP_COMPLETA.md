# Descripción GBP completa

## Problema observado

En algunos productos, `WebSite_Description` llega desde `wsItem_funGetXMLDataById` limitado a aproximadamente 100 caracteres. Ejemplo: SKU `6130BL` quedaba publicado como:

```text
SOMOS SILMAR BAZAR ONLINE•Realizamos envíos a todo el pais, podes ver la fecha de entrega estimada
```

pero en GBP la descripción visible es mucho más larga.

## Corrección

El normalizador ahora mantiene `WebSite_Description` como fuente principal, pero detecta si existe una extensión completa en `item_detail` únicamente cuando:

1. `item_detail` es mucho más largo.
2. `item_detail` comparte el prefijo textual de `WebSite_Description`.
3. Por lo tanto, `item_detail` no se usa como descripción genérica de rubro o contenido interno.

Esto conserva la decisión de negocio: no usar `item_detail` salvo cuando demuestra ser la continuación exacta de la descripción web truncada.

## Diagnóstico agregado

Endpoint:

```http
POST /sync/audit/gbp-product-description-debug?sku=6130BL
```

No escribe en Tienda Nube. Devuelve:

```text
descripcion_seleccionada_largo
descripcion_seleccionada_preview
campos_relevantes[] con campo, largo, preview y si es candidato web
```

## Validación previa a importar

```powershell
Invoke-RestMethod -Method Post -Uri "https://gbp-tn-sync.onrender.com/sync/audit/gbp-product-description-debug?sku=6130BL"
```

Luego verificar que `descripcion_seleccionada_largo` sea mayor a 100 y que el preview contenga la parte específica del producto.
