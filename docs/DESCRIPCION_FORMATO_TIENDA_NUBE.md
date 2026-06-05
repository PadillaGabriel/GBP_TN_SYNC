# Descripción con formato en Tienda Nube

## Problema

GBP devuelve la descripción completa con saltos de línea, viñetas y separadores.
Si se envía como texto plano al campo `description` de Tienda Nube, el navegador colapsa los saltos de línea y la publicación queda visualmente apretada.

## Solución aplicada

El integrador conserva la descripción normalizada como texto interno, pero al construir el payload para Tienda Nube la convierte a HTML seguro.

Archivo:

```text
app/infrastructure/tienda_nube/payload_builder.py
```

Reglas:

```text
líneas separadas por blanco -> párrafos <p>
saltos simples dentro de un bloque -> <br>
separadores largos de =, -, _, * -> <hr>
HTML crudo de GBP -> escapado con html.escape
```

Ejemplo:

```text
SOMOS SILMAR BAZAR ONLINE

•Realizamos envíos...
•Si estas en CABA...

============================================================
DISPENSER JABON LIQUIDO DE CERAMICA
```

Se envía a Tienda Nube como:

```html
<p>SOMOS SILMAR BAZAR ONLINE</p>
<p>•Realizamos envíos...<br>•Si estas en CABA...</p>
<hr>
<p>DISPENSER JABON LIQUIDO DE CERAMICA</p>
```

## Seguridad

No se permite HTML crudo de GBP. Se escapan caracteres como `<`, `>` y `&` para evitar inyección de markup no controlado.
