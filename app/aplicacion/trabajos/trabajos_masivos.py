"""Facade compatible: implementaciones separadas por responsabilidades.

La única ejecución de jobs debe ocurrir en app.procesos.worker.
"""
from app.aplicacion.trabajos.auditoria import ejecutar_job_auditar_todo, ejecutar_job_auditar_proximos, ejecutar_job_reauditar_decision
from app.aplicacion.trabajos.importacion import ejecutar_job_importar_todo, ejecutar_job_importar_pendientes, ejecutar_job_importar_sku
from app.aplicacion.trabajos.stock import ejecutar_job_stock_lote, ejecutar_job_stock_sku, ejecutar_job_stock_incremental
from app.aplicacion.trabajos.categorias import ejecutar_job_normalizar_categorias
from app.aplicacion.trabajos.reconciliacion import ejecutar_job_reconciliar_tienda_nube
