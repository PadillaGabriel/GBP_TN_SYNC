class IntegradorError(Exception):
    """Error base controlado del integrador."""


class MetodoNoValidadoError(IntegradorError):
    """El método GBP no está validado para Módulo 16."""


class DatoIncompletoError(IntegradorError):
    """La fuente externa devolvió datos incompletos."""


class SincronizacionError(IntegradorError):
    """Error controlado durante una sincronización."""
