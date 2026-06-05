from decimal import Decimal
from typing import Any

from app.domain.errors import DatoIncompletoError
from app.domain.models.imagen import ImagenProducto
from app.domain.models.medidas import MedidasProducto
from app.domain.models.precio import PrecioProducto
from app.domain.models.producto import Producto
from app.domain.models.stock import StockDeposito, StockProducto
from app.infrastructure.gbp.xml_parser import normalizar_texto_gbp


class GBPNormalizer:
    """Convierte respuestas GBP en modelos internos neutrales."""

    def normalizar_producto(self, data: dict[str, Any]) -> Producto:
        """Normaliza producto completo desde campos GBP validados."""

        sku = self._require_str(data, "item_code")
        id_sistema = self._require_str(data, "item_id")
        titulo = self._require_str(data, "item_desc")
        precio = data.get("precio_online")
        return Producto(
            sku=sku,
            id_sistema_gbp=id_sistema,
            codigo_universal=self._optional_str(data, "item_barcode"),
            codigo_proveedor=self._optional_str(data, "item_vendorCode"),
            titulo=titulo,
            categoria_nombre=self._optional_str(data, "cat_desc"),
            subcategoria_nombre=self._optional_str(data, "subcat_desc"),
            marca_nombre=self._optional_str(data, "brand_desc"),
            publicable_web=self._to_bool_or_none(data.get("item_web")),
            item_disabled=self._to_bool(data.get("item_disabled")),
            item_not_for_sale=self._to_bool(data.get("item_not4Sale")),
            descripcion_web=self._optional_str(data, "WebSite_Description"),
            medidas=MedidasProducto(
                alto=self._to_decimal_or_none(data.get("item_higth")),
                ancho=self._to_decimal_or_none(data.get("item_wide")),
                largo=self._to_decimal_or_none(data.get("item_large")),
                peso=self._to_decimal_or_none(data.get("item_weight")),
                volumen=self._to_decimal_or_none(data.get("item_volume")),
            ),
            precio_importado=(
                PrecioProducto(monto=Decimal(str(precio)), lista_precio_id=str(data.get("prli_id", "")))
                if precio not in (None, "")
                else None
            ),
            imagenes=self._normalizar_imagenes(data),
        )

    def normalizar_stock(self, data: dict[str, Any]) -> StockProducto:
        """Normaliza stock operativo usando el campo Stock de GBP."""

        sku = self._require_str(data, "sku")
        cantidad = data.get("stock")
        if cantidad is None:
            raise DatoIncompletoError("GBP no devolvio stock disponible")
        stock_tn = max(0, int(float(cantidad)))
        return StockProducto(
            sku=sku,
            id_sistema_gbp=self._optional_str(data, "id_sistema_gbp"),
            cantidad=stock_tn,
            stock_original_gbp=float(cantidad),
            depositos=[
                StockDeposito(
                    stor_id=str(data.get("stor_id", "")),
                    stock_disponible=stock_tn,
                    stock_original=float(cantidad),
                    usado_para_tienda_nube=True,
                )
            ],
        )

    @staticmethod
    def _normalizar_imagenes(data: dict[str, Any]) -> list[ImagenProducto]:
        imagenes: list[ImagenProducto] = []
        for index in range(1, 11):
            url = str(data.get(f"item_WebSite_url4Image{index}") or "").strip()
            if url:
                imagenes.append(ImagenProducto(url=url, orden=index))
        return imagenes

    @staticmethod
    def _require_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if value is None or str(value).strip() == "":
            raise DatoIncompletoError(f"GBP no devolvio el campo obligatorio: {key}")
        return normalizar_texto_gbp(str(value))

    @staticmethod
    def _optional_str(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None or str(value).strip() == "":
            return None
        return normalizar_texto_gbp(str(value))

    @staticmethod
    def _to_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "1", "yes", "si", "sí"}

    @classmethod
    def _to_bool_or_none(cls, value: object) -> bool | None:
        if value is None or str(value).strip() == "":
            return None
        return cls._to_bool(value)

    @staticmethod
    def _to_decimal_or_none(value: object) -> Decimal | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
