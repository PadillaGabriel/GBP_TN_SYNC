# Auditoría técnica de limpieza y rendimiento

## Cambios aplicados

### Panel administrativo

- Se eliminó el desborde horizontal del layout principal.
- Se separaron controles en tarjetas funcionales:
  - Filtros
  - Importación puntual por SKU
  - Operaciones de auditoría/importación
  - Mantenimiento
- Se dejó el scroll horizontal únicamente dentro de la tabla, no en toda la pantalla.
- Se compactó la grilla de botones y se eliminaron botones sueltos fuera del panel de filtros.
- Se mantuvieron las confirmaciones antes de acciones destructivas.

### Limpieza de código

- Se eliminó código HTML embebido viejo de `routes_admin.py` que ya no se usaba desde que el panel pasó a Jinja2.
- Se eliminaron helpers muertos asociados a ese render legacy.
- Se quitó un import innecesario de `html.escape`.

### Rendimiento del panel

- Se corrigió una consulta N+1 en `listar_panel_decisiones`.
- Antes: la tabla consultaba stock una vez por producto visible.
- Ahora: el stock publicable se trae en el mismo `SELECT` mediante `LEFT JOIN` a `stock_actual`.
- Impacto: menor latencia de panel y menos carga sobre PostgreSQL.

## Validación ejecutada

```bash
pytest -q
# 30 passed

python -m compileall -q app
# sin errores
```

## Pendientes recomendados para una segunda auditoría

- Agregar índices explícitos en base si el volumen crece:
  - `productos_fuente.sku`
  - `producto_validaciones.producto_fuente_id`
  - `producto_validaciones.decision`
  - `productos_tienda_nube.sku`
  - `productos_tienda_nube.estado_publicacion`
  - `stock_actual.producto_fuente_id`
- Medir tiempos reales del panel con 3.694 auditados y filtros comunes.
- Revisar logs de jobs largos para detectar productos con latencias GBP anómalas.
- Separar futuras acciones masivas en jobs si alguna request manual supera timeout de Render.
