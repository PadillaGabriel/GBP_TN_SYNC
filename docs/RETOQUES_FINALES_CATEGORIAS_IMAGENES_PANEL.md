# Retoques finales: categorías, imágenes, panel y reauditoría

## Categorías duplicadas

Se agregó normalización defensiva de categorías para evitar crear duplicados por:

- mayúsculas/minúsculas
- acentos
- espacios
- mojibake
- alias simples como `Baño`, `BANO`, `banio`
- variantes como `Accesorios baño` / `Accesorios de baño`

El importador ahora busca categorías por clave canónica antes de crear nuevas.

También se agregó acción de mantenimiento:

```http
POST /admin/panel/categorias/normalizar-duplicadas
```

Desde el panel aparece como:

```text
Normalizar categorías
```

Esa acción reasigna productos a categorías canónicas e intenta eliminar categorías duplicadas vacías en Tienda Nube.

## Imágenes normalizadas

Se agregó endpoint público para generar imagen cuadrada con padding blanco:

```http
GET /media/normalized-image?src=URL_ORIGINAL&size=1600
```

No recorta, no deforma y no estira el producto. Centra la imagen original dentro de un canvas blanco cuadrado.

Variables nuevas:

```env
APP_PUBLIC_BASE_URL=https://gbp-tn-sync.onrender.com
IMAGE_NORMALIZATION_ENABLED=true
IMAGE_NORMALIZATION_CANVAS_SIZE=1600
```

Si `IMAGE_NORMALIZATION_ENABLED=false`, se siguen enviando las URLs originales de GBP.

## Panel más ordenado

Se reemplazaron los botones de filtros por un desplegable:

```text
Estado
Buscar
Límite
Aplicar
```

Esto mejora la lectura para usuarios que no conocen el proyecto.

## Reauditar productos sin descripción

Se agregó acción:

```text
Reauditar sin descripción
```

Uso: cuando se agregan descripciones nuevas en GBP para productos previamente bloqueados por `NO_PUBLICAR_SIN_DESCRIPCION_WEB`.

La acción reconsulta esos SKUs en GBP, vuelve a validar y deja como `PUBLICABLE_AUTOMATICO` los que ahora cumplen las reglas.
