from __future__ import annotations

from app.configuracion import ConfiguracionAplicacion
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube


class FabricaAdaptadorTiendaNube:
    """Construye el adaptador de Tienda Nube desde la configuración central."""

    def __init__(self, configuracion: ConfiguracionAplicacion) -> None:
        self._configuracion = configuracion

    def crear(self) -> AdaptadorTiendaNube:
        cliente = ClienteTiendaNube(
            base_url=self._configuracion.tienda_nube_base_url,
            store_id=self._configuracion.tienda_nube_store_id,
            access_token=self._configuracion.tienda_nube_access_token,
            timeout_seconds=self._configuracion.tienda_nube_timeout_seconds,
        )
        return AdaptadorTiendaNube(
            client=cliente,
            image_normalization_enabled=self._configuracion.image_normalization_enabled,
            image_normalization_base_url=self._configuracion.app_public_base_url,
            image_normalization_canvas_size=self._configuracion.image_normalization_canvas_size,
        )
