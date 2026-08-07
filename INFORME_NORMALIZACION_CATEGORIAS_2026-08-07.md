# Normalización comercial de categorías

## Objetivo

Separar el dato fuente de GBP de la taxonomía comercial utilizada en Tiendanube y evitar que variantes textuales creen categorías duplicadas.

## Implementación

- Nueva tabla `categoria_normalizaciones` en la base de datos.
- Diccionario administrable para `categoria` y `subcategoria`.
- Resolución por clave normalizada, con contexto opcional de categoría padre para subcategorías.
- El adaptador Tiendanube resuelve el nombre canónico antes de buscar o crear categorías.
- El normalizador correctivo de Tiendanube utiliza el mismo diccionario comercial al fusionar duplicados existentes.
- Nueva pantalla Enterprise `/admin/panel/categorias`.
- Diagnóstico y ejecución de normalización desde botones POST; abrir por GET la antigua URL de acción redirige a la pantalla y evita 405.

## Seguridad funcional

- No se modifica el valor original recibido desde GBP.
- El diccionario solo cambia el nombre comercial usado para resolver/publicar categorías.
- El diagnóstico (`confirm=false`) no escribe en Tiendanube.
- La normalización real (`confirm=true`) reasigna productos y elimina duplicados según el flujo ya existente.
