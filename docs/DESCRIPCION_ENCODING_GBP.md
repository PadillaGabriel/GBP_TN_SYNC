# Descripción GBP completa y encoding

## Resultado validado

El endpoint de diagnóstico confirmó que `WebSite_Description` puede venir truncado a aproximadamente 100 caracteres.

Para SKU `6130BL`, GBP devolvió:

- `WebSite_Description`: descripción corta.
- `WebSite_ShortDescription`: descripción completa.
- `item_descHTML`: descripción completa, pero no se toma como fuente principal si hay campo Web válido.

La fuente operativa correcta para descripción completa queda en el selector de campos web descriptivos, priorizando el contenido más largo y útil.

## Corrección de mojibake

Se reforzó `normalizar_texto_gbp` para reparar textos GBP con UTF-8 mal interpretado como Latin-1/Windows-1252.

Casos cubiertos:

- `â¢` / `â€¢` -> `•`
- `envÃos` -> `envíos`
- `mÃ¡s` -> `más`
- `dÃa` -> `día`
- `CerÃ¡mica` -> `Cerámica`
- `plÃ¡stico` -> `plástico`
- `jabÃ³n` -> `jabón`
- `LanÃºs` -> `Lanús`

## Validación

Ejecutar:

```powershell
Invoke-RestMethod -Method Post -Uri "https://gbp-tn-sync.onrender.com/sync/audit/gbp-product-description-debug?sku=6130BL"
```

Resultado esperado:

- `descripcion_seleccionada_largo` mayor a 1000.
- `descripcion_seleccionada_preview` con bullets `•`.
- Acentos correctos en `envíos`, `más`, `día`, `Cerámica`, `plástico`, `jabón`, `Lanús`.
