# Reglas finales de negocio

## Fuente canónica

GBP es la fuente canónica. Tienda Nube es destino de publicación.

## Selección de productos

Candidato inicial:

```text
Tiene al menos una imagen Website en ItemBasicData_funGetXMLData
```

Publicable automático:

```text
item_web == true
item_disabled != true
item_not4Sale != true
WebSite_Description no vacía
precio online válido
stock disponible consultable
SKU válido
título válido
```

## Descripción

Campo obligatorio:

```text
WebSite_Description
```

No usar:

```text
item_detail
```

## Código proveedor

```text
item_vendorCode -> codigo_proveedor
```

No usar como SKU.

## SKU

```text
item_code -> sku
```

## Categoría, subcategoría y marca

Guardar nombres, no solo IDs:

```text
cat_desc
subcat_desc
brand_desc
```

## Stock

Usar stock disponible, no stock general.

Campo fuente:

```text
Stock
```

No usar como stock publicable:

```text
FS
FS4StorageGroup
stock físico bruto
```

Cálculo:

```text
stock_tn = max(0, suma de Stock en depósitos habilitados para ecommerce)
```

## Precio

Solo importación inicial o actualización completa manual.

No sincronización frecuente de precio.

## Panel admin

Debe mostrar por producto:

```text
imagen Website
item_web
item_disabled
item_not4Sale
WebSite_Description
precio online
stock disponible
SKU
título
decisión final
motivos de bloqueo
```
