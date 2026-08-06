from decimal import Decimal, InvalidOperation
import re
from typing import Any

from app.dominio.errores import DatoIncompletoError
from app.dominio.modelos.imagen import ImagenProducto
from app.dominio.modelos.medidas import MedidasProducto
from app.dominio.modelos.precio import PrecioProducto
from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockDeposito, StockProducto
from app.infraestructura.gbp.analizador_xml import normalizar_texto_gbp


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
            descripcion_web=self._extract_web_description(data),
            medidas=MedidasProducto(
                alto=self._to_decimal_or_none(data.get("item_higth")),
                ancho=self._to_decimal_or_none(data.get("item_wide")),
                largo=self._to_decimal_or_none(data.get("item_large")),
                peso=self._to_decimal_or_none(data.get("item_weight")),
                volumen=self._to_decimal_or_none(data.get("item_volume")),
            ),
            precio_importado=(
                PrecioProducto(
                    monto=Decimal(str(precio)),
                    lista_precio_id=str(data.get("prli_id", "")),
                )
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

        stor_ids = {
            str(item).strip() for item in ecommerce_storage_ids if str(item).strip()
        }
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

    @classmethod
    def _extract_web_description(cls, data: dict[str, Any]) -> str | None:
        """Extrae la descripcion web real desde campos GBP candidatos.

        GBP puede devolver la descripcion completa bajo nombres variables de
        campos Website/Web + Description/Desc. No se usa item_detail como fuente
        operativa porque esa decision de negocio sigue cerrada. Si aparecen
        varios campos web descriptivos, se elige el contenido mas largo y
        completo, evitando campos de imagen, URL, titulo o metadata.
        """

        candidates: list[tuple[str, str]] = []
        for key, value in data.items():
            if value is None or str(value).strip() == "":
                continue
            if not cls._is_web_description_key(str(key)):
                continue
            text = normalizar_texto_gbp(str(value))
            if text:
                candidates.append((str(key), text))

        if not candidates:
            return cls._optional_str(data, "WebSite_Description")

        # Si GBP parte el texto en campos numerados, unirlos en orden.
        grouped = cls._merge_description_chunks(candidates)
        if grouped:
            selected = grouped
        else:
            # En caso de campos alternativos, usar el de mayor longitud útil.
            selected = max(candidates, key=lambda item: len(item[1]))[1]

        # Caso observado en GBP: WebSite_Description puede venir limitado a ~100
        # caracteres, mientras que item_detail trae la misma descripción completa.
        # La regla de negocio sigue siendo no usar item_detail genérico; solo se
        # acepta como extensión cuando comparte el prefijo de la descripción web.
        detail_extension = cls._detail_if_extends_web_description(data, selected)
        return detail_extension or selected

    @classmethod
    def _detail_if_extends_web_description(
        cls, data: dict[str, Any], selected: str
    ) -> str | None:
        detail = cls._optional_str(data, "item_detail")
        if not detail or not selected:
            return None
        if len(detail) <= max(len(selected) + 50, 180):
            return None

        selected_key = cls._comparison_prefix(selected)
        detail_key = cls._comparison_prefix(detail)
        if not selected_key or not detail_key:
            return None
        if (
            detail_key.startswith(selected_key)
            or selected_key in detail_key[: max(120, len(selected_key) + 20)]
        ):
            return detail
        return None

    @staticmethod
    def _comparison_prefix(value: str) -> str:
        text = normalizar_texto_gbp(value)
        text = re.sub(r"\s+", " ", text).strip().lower()
        text = re.sub(r"[^a-z0-9áéíóúüñ ]", "", text)
        return text[:80].strip()

    @staticmethod
    def _is_web_description_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized == "websitedescription":
            return True
        if "itemdetail" in normalized:
            return False
        if any(
            excluded in normalized
            for excluded in (
                "image",
                "url",
                "title",
                "name",
                "meta",
                "category",
                "brand",
            )
        ):
            return False
        has_web = (
            "website" in normalized
            or normalized.startswith("web")
            or "web" in normalized
        )
        has_desc = (
            "description" in normalized
            or "descripcion" in normalized
            or normalized.endswith("desc")
        )
        return has_web and has_desc

    @staticmethod
    def _merge_description_chunks(candidates: list[tuple[str, str]]) -> str | None:
        chunked: list[tuple[int, str]] = []
        for key, text in candidates:
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            match = re.search(
                r"(websitedescription|webdescription|website_desc|webdesc)([0-9]+)$",
                normalized,
            )
            if match:
                chunked.append((int(match.group(2)), text))

        if len(chunked) < 2:
            return None

        parts: list[str] = []
        for _, text in sorted(chunked, key=lambda item: item[0]):
            if not any(text == existing or text in existing for existing in parts):
                parts.append(text)
        return "\n".join(parts).strip() or None

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
