from decimal import Decimal, InvalidOperation
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
        stock = data.get("stock_producto")
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
            stock=stock if isinstance(stock, StockProducto) else None,
            imagenes=self._normalizar_imagenes(data),
        )

    def normalizar_precio(
        self,
        rows: list[dict[str, Any]],
        *,
        price_list_id: int | str,
    ) -> PrecioProducto | None:
        """Normaliza precio online desde filas de PriceListItems_*.

        GBP puede variar nombres de columnas según instalación. Se priorizan
        campos conocidos y luego cualquier campo numérico cuyo nombre contenga
        price/precio, evitando IDs.
        """

        amount: Decimal | None = None
        price_row: dict[str, Any] | None = None
        for row in rows:
            amount = self._extraer_precio_de_fila(row)
            if amount is not None:
                price_row = row
                break

        if amount is None or amount <= Decimal("0"):
            return None

        return PrecioProducto(
            monto=amount,
            lista_precio_id=str(price_list_id),
            lista_precio_nombre=self._optional_str(price_row or {}, "prli_desc"),
        )

    def normalizar_stock_desde_filas(
        self,
        rows: list[dict[str, Any]],
        *,
        sku: str,
        id_sistema_gbp: str,
        ecommerce_storage_ids: list[str],
    ) -> StockProducto:
        """Normaliza stock disponible usando campo Stock y depósitos ecommerce."""

        if not rows:
            raise DatoIncompletoError("GBP no devolvió filas de stock")

        stor_ids = {str(item).strip() for item in ecommerce_storage_ids if str(item).strip()}
        depositos: list[StockDeposito] = []
        total_original = Decimal("0")
        tiene_deposito_usado = False

        for row in rows:
            stor_id = self._optional_str(row, "stor_id") or ""
            stock_value = self._to_decimal_or_none(row.get("Stock"))
            if stock_value is None:
                continue

            usado = bool(stor_ids) and stor_id in stor_ids
            if usado:
                total_original += stock_value
                tiene_deposito_usado = True

            depositos.append(
                StockDeposito(
                    stor_id=stor_id,
                    stock_disponible=max(0, int(stock_value)),
                    stock_original=float(stock_value),
                    usado_para_tienda_nube=usado,
                )
            )

        if not depositos:
            raise DatoIncompletoError("GBP no devolvió stock disponible utilizable")

        stock_tn = max(0, int(total_original)) if tiene_deposito_usado else 0
        return StockProducto(
            sku=sku,
            id_sistema_gbp=id_sistema_gbp,
            cantidad=stock_tn,
            stock_original_gbp=float(total_original) if tiene_deposito_usado else None,
            depositos=depositos,
        )

    def normalizar_stock(self, data: dict[str, Any]) -> StockProducto:
        """Normaliza una fila simple de stock operativo usando campo Stock."""

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

    @classmethod
    def _extraer_precio_de_fila(cls, row: dict[str, Any]) -> Decimal | None:
        known_keys = (
            "price",
            "Price",
            "PRICE",
            "precio",
            "Precio",
            "PRECIO",
            "prliitem_price",
            "prlii_price",
            "pli_price",
            "item_price",
            "sale_price",
            "price_value",
        )
        for key in known_keys:
            value = cls._to_decimal_or_none(row.get(key))
            if value is not None:
                return value

        for key, value in row.items():
            key_lower = str(key).lower()
            if "id" in key_lower or "code" in key_lower:
                continue
            if "price" in key_lower or "precio" in key_lower:
                parsed = cls._to_decimal_or_none(value)
                if parsed is not None:
                    return parsed
        return None

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
        text = str(value).strip().replace("$", "").replace(" ", "")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None
