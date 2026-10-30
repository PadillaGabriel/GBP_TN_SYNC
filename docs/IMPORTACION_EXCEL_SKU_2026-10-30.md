# Importación masiva de SKU desde Excel

## Alcance

Esta versión incorpora una carga `.xlsx` en **Importaciones → Importar SKU desde Excel**, para publicar o actualizar SKU existentes en GBP en Tiendanube mediante los jobs `IMPORTAR_SKU_TN` y su worker duradero.

No es un importador de pedidos, ni fuerza la creación de productos bloqueados, ni actualiza clientes GBP. Tampoco garantiza resultados en producción hasta comprobar la configuración del worker y de escritura.

## Formato

- Archivo Excel `.xlsx`, hasta 2 MB y 500 SKU.
- Primera hoja: `A1 = SKU`; un SKU por fila en la columna A.
- No se permiten fórmulas ni códigos con espacios; SKU numéricos con ceros iniciales deben guardarse como texto.
- Se ignoran filas vacías y se omiten duplicados internos (sin distinguir mayúsculas/minúsculas).
- La validación se muestra antes de habilitar la confirmación.

## Operación

1. Abrir Importaciones, elegir Excel y presionar **Validar Excel**.
2. Revisar cantidad, duplicados y muestra.
3. Presionar **Confirmar importación** y aceptar.
4. Se crea un job `IMPORTAR_SKU_TN` por SKU con un identificador de lote en `progreso_json`.
5. Inspeccionar resultados en **Trabajos**. El resultado de la API es `encolado`, no significa importación completada.

## Seguridad y límites

- El servidor valida el XLSX nuevamente al confirmar; nunca ejecuta fórmulas, macros ni datos de columnas comerciales.
- Reutiliza el proceso de validación, `dry_run` y salvaguardas del importador individual.
- No existe una transacción atómica para todo el lote: `RepositorioTrabajosSincronizacion.crear` confirma cada trabajo por separado. Si falla la solicitud a mitad de creación, pueden quedar trabajos encolados parcialmente. Antes de reintentar, verificar en el listado de Trabajos.
- Repetir una carga deliberadamente crea nuevos trabajos; el comportamiento idempotente de cada SKU se determina en el importador de destino. No se debe asumir un control de idempotencia por archivo.
- No exponer la importación sin la protección de autenticación del panel existente.

## Pruebas realizadas

Pruebas Python de la base del proyecto + cinco pruebas del parser XLSX. Sin validación de extremo a extremo contra GBP o Tiendanube productivos.
