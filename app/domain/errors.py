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


class TiendaNubeHTTPError(IntegradorError):
    """Error HTTP controlado de Tienda Nube con detalle de request/response."""

    def __init__(
        self,
        *,
        status_code: int,
        url: str,
        response_text: str,
        request_body: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self.response_text = response_text
        self.request_body = request_body
        super().__init__(
            f"Tienda Nube HTTP {status_code} url={url} response={response_text[:1000]}"
        )
