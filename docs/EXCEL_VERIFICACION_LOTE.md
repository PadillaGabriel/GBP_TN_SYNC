# Verificación consolidada de importaciones Excel

El importador Excel conserva su `lote_excel` en el `payload_json` de los trabajos `IMPORTAR_SKU_TN`, que no se sobrescribe con los cambios de progreso. No requiere migración de base de datos.

Tras una importación **real** exitosa, con mapeo local activo y variante resuelta, el worker crea de modo idempotente un trabajo `STOCK_SYNC_SKU` identificado mediante `excel-stock:{id_trabajo_importacion}`. No lo crea en modo `DRY_RUN` ni para un mapeo inválido. Se respetan los controles propios del servicio de stock.

`GET /admin/panel/importar-excel/lotes/{lote}` devuelve resumen y resultados por SKU. Solo considera **sincronizado** a un SKU cuando el trabajo de stock generado a partir de esa importación terminó exitosamente con estado `ACTUALIZADO`, `ACTUALIZADO_MAPEO_REPARADO` o `SIN_CAMBIOS`, y existe un mapeo activo con producto y variante. Los resultados son operativos, basados en los registros persistidos por el integrador; **no sustituyen una lectura de confirmación remota de Tiendanube**. Si el trabajo aún no terminó, se indica pendiente. Los errores se muestran como fallidos. Los resultados simulados no se presentan como sincronizados.

La página Importaciones incluye resumen por lote y detalle de filas, actualizado periódicamente durante la consulta. El endpoint de lote no reconstruye lotes Excel anteriores a esta versión cuyos trabajos no conservaron el identificador en `payload_json`.

Para prueba real en Railway: aplicar el parche sobre la entrega `GBP_TN_SYNC_importador_excel_completo.zip` (no sobre una versión anterior); comprobar que WEB y WORKER están usando la misma versión; cargar 1–2 SKU de prueba; verificar vínculo en Tiendanube y estado final en la tabla; comprobar que las políticas de DRY_RUN y escritura sean las esperadas. No se ejecutaron escrituras remotas en esta entrega.
