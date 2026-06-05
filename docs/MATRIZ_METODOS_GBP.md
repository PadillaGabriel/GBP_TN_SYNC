# Matriz inicial de métodos GBP para Integrador GBP -> Tienda Nube

Estado del documento: matriz técnica inicial para validación real con credenciales.
Regla: ningún método queda habilitado para producción hasta registrar respuesta real, campos devueltos, latencia, volumen, pertenencia efectiva al Módulo 16 y utilidad funcional.

## Criterios de evaluación

| Criterio | Interpretación |
|---|---|
| Pertinencia funcional | El método trae datos necesarios para publicar o sincronizar en Tienda Nube. |
| Costo operativo | Tamaño de respuesta, tiempo de ejecución, frecuencia posible. |
| Riesgo contractual | Debe estar permitido por Módulo 16. |
| Riesgo técnico | XML inválido, respuesta incompleta, campos ambiguos, dependencia de parámetros. |
| Uso recomendado | Import inicial, cache auxiliar, sync frecuente de stock, acción manual. |

## Matriz

| Necesidad | Método candidato | Parámetros principales | Módulo declarado | Uso propuesto | Frecuencia | Estado inicial | Decisión técnica inicial |
|---|---|---:|---|---|---|---|---|
| Autenticación | `AuthenticateUser` | Header GBP | 16 operativo | Autenticación | Antes de toda corrida | Candidato obligatorio | Medir latencia y formato de token. |
| Descubrir productos | `ItemBasicData_funGetXMLData` | `bitOnlyNewOrUpdated` | 16 | Detectar artículos básicos | Manual / inicial / incremental | Candidato fuerte | Probar primero con `True`; usar `False` solo para carga completa. |
| Descubrir productos | `Item_funGetXMLData_Short` | sin parámetros | 16 | Lista corta de artículos | Import inicial | Candidato fuerte | Comparar contra `ItemBasicData_funGetXMLData` por volumen y campos. |
| Producto completo | `wsItem_funGetXMLDataById` | `intItemID` | 16 | Ficha completa por artículo | Import inicial / actualización completa manual | Candidato principal | Usar por artículo; no usar en ciclo frecuente. |
| Resolver SKU a ID GBP | `wsgetItemIDfromCode_funGetXMLData` | `strItemCode` | 16 | Obtener ID interno desde código/SKU | Bajo demanda | Candidato fuerte | Validar si `strItemCode` corresponde exactamente al SKU operativo. |
| Stock frecuente | `ItemStorage_funGetXMLData` | `intStor_id`, `intItem_id` | 16 | Stock por artículo o depósito | Frecuente | Candidato principal | Priorizar consulta por `intItem_id`; evitar `-1/-1` en ciclo frecuente salvo benchmark. |
| Imágenes | `wsGetWebSiteImagesURL4WebServices` | `intItemID`, `bolIsAvailable4Web`, `bolIsAvailable4FulljausAndProducteca` | 16 / 45 / 78 | URLs de imágenes para web | Import inicial / manual | Candidato fuerte | Usar `bolIsAvailable4Web=True` y el otro booleano en `False`. |
| Imágenes | `ItemImages_funGetXMLData` | `intItemId` | 16 | Imágenes por artículo o todos activos | Import inicial / manual | Candidato alternativo | Comparar contra `wsGetWebSiteImagesURL4WebServices`. |
| Precio inicial | `PriceList_funGetXMLData` | sin parámetros | 16 | Obtener listas de precio | Cache auxiliar | Diario / manual | Candidato necesario | Identificar lista correcta antes de leer precios. |
| Precio inicial | `PriceListItems_funGetXMLData_Short` | `pPriceList`, `pItem` | 16 | Precio por lista/artículo | Import inicial / actualización completa manual | Candidato principal | No usar en sync frecuente. Probar por `pItem` y lista específica. |
| Categorías | `Category_funGetXMLData` | sin parámetros | 16 | Cache de categorías | Cache auxiliar | Diario / manual | Candidato fuerte | Cachear localmente. |
| Subcategorías | `SubCategory_funGetXMLData` | sin parámetros | 16 | Cache de subcategorías | Cache auxiliar | Diario / manual | Candidato fuerte | Cachear localmente. |
| Marcas | `Brand_funGetXMLData` | sin parámetros | 16 | Cache de marcas | Cache auxiliar | Diario / manual | Candidato fuerte | Cachear localmente. |
| Unidades | `MeasurementUnits_funGetXMLData` | sin parámetros | 16 | Cache de unidades | Cache auxiliar | Diario / manual | Candidato fuerte | Cachear localmente. |
| Últimos cambios | `ws_GetLatestItemsUpdated` | último ID de consulta | 16 | Incremental teórico | Controlado | Candidato a validar | Evaluar después de stock por artículo; no depender hasta entender cursor y depuración 24 h. |
| V2 artículos | `wsV2_Item_funGetXMLData` | `intItemID`, `bolAllAvailableItems` | 16 condicionado | Incremental o total | Controlado | NO USAR HASTA VALIDAR | Solo funciona si la base termina en `_TIU`; validar antes. |

## Métodos descartados para el diseño principal

| Prefijo / método | Motivo |
|---|---|
| `MercadoLibre_*` | Módulo 45 y dependencia directa de ML. Contradice la arquitectura objetivo. |
| `Producteca_*` | Módulo 45. Fuera del alcance principal. |
| `FullJaus_*` | Módulo 78. Fuera del alcance principal. |
| Métodos `Set*` | Escritura en GBP. Prohibidos para el diagnóstico inicial. |

## Regla de frecuencia

| Dato | Momento de consulta |
|---|---|
| Stock | Frecuente. Scheduler. Solo compara y actualiza diferencias. |
| Precio | Import inicial o actualización completa manual. No frecuente. |
| Fotos | Import inicial o actualización completa manual. No frecuente. |
| Descripción | Import inicial o actualización completa manual. No frecuente. |
| Categoría | Cache auxiliar. No por cada producto si puede evitarse. |
| Marca / unidades | Cache auxiliar. |

## Resultado esperado del script temporal

El script debe producir evidencia en `diagnostics/gbp/`:

- `gbp_diagnostic_results.jsonl`: un registro por método ejecutado.
- `gbp_diagnostic_summary.csv`: resumen tabular para comparar tiempos, tamaños y errores.
- `raw/`: respuestas crudas solo si se ejecuta con `--save-raw`.

Cada registro debe incluir:

- método;
- parámetros;
- estado HTTP;
- duración en milisegundos;
- tamaño de respuesta SOAP;
- tamaño del resultado interno;
- cantidad aproximada de nodos XML;
- campos detectados;
- preview seguro;
- error, si existe;
- decisión pendiente.
