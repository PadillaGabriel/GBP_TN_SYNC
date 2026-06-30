class IntegradorError(Exception):
    """Error base controlado del integrador."""


class MetodoNoValidadoError(IntegradorError):
    """El método GBP no está validado para Módulo 16."""


class DatoIncompletoError(IntegradorError):
    """La fuente externa devolvió datos incompletos."""


class SincronizacionError(IntegradorError):
    """Error controlado durante una sincronización."""

class GBPProductoNoConsultableError(IntegradorError):
    """GBP resolvió el producto, pero no devolvió ficha completa consultable."""


class GBPSkuNoResueltoError(IntegradorError):
    """GBP no devolvió item_id para el SKU informado."""