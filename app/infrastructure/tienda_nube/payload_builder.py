from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import html
import re
from typing import Any
from urllib.parse import quote

from app.domain.models.producto import Producto
from app.infrastructure.gbp.xml_parser import normalizar_texto_gbp


class TiendaNubePayloadBuilder:
    """Construye payloads de Tienda Nube desde modelos internos.

    Separación intencional:
    - create_product: puede incluir variantes e imágenes.
    - update_product: solo datos del producto, nunca variantes.
    - update_variant: precio/stock/SKU/barcode de la variante.

    Esto evita errores 422 por enviar variantes/imágenes completas al endpoint
    `/products/{id}` cuando el producto ya existe.
    """

    def __init__(
        self,
        *,
        image_normalization_enabled: bool = False,
        image_normalization_base_url: str = "",
        image_normalization_canvas_size: int = 1600,
    ) -> None:
        self.image_normalization_enabled = image_normalization_enabled
        self.image_normalization_base_url = image_normalization_base_url.rstrip("/")
        self.image_normalization_canvas_size = image_normalization_canvas_size

    def build_product_payload(
        self,
        producto: Producto,
        *,
        category_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Compatibilidad legacy: payload completo para crear producto."""

        return self.build_create_product_payload(producto, category_ids=category_ids)

    def build_create_product_payload(
        self,
        producto: Producto,
        *,
        category_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Payload completo para crear producto.

        La creación sí incluye la variante principal y, si existen, imágenes.
        """

        payload = self.build_update_product_payload(producto, category_ids=category_ids)
        payload["variants"] = [self.build_create_variant_payload(producto)]

        if producto.imagenes:
            images = [
                {"src": self._build_image_url(str(imagen.url))}
                for imagen in sorted(producto.imagenes, key=lambda item: item.orden)
                if imagen.url is not None and str(imagen.url).strip()
            ]
            if images:
                payload["images"] = images

        return payload

    def build_update_product_payload(
        self,
        producto: Producto,
        *,
        category_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Payload seguro para actualizar producto existente.

        No incluye `variants` ni `images`. Las variantes se actualizan mediante
        endpoint de variantes; las imágenes no se reenvían en cada actualización
        para evitar duplicados y rechazos 422.
        """

        payload: dict[str, Any] = {
            "name": {"es": normalizar_texto_gbp(producto.titulo)},
            "description": {"es": self._format_description_html(producto.descripcion_web)},
        }

        if category_ids:
            payload["categories"] = category_ids

        return payload

    def build_create_variant_payload(self, producto: Producto) -> dict[str, Any]:
        """Payload de variante para creación.

        En creación, si GBP no devolvió precio/stock se envía precio 0 y stock 0
        para permitir publicación manual sin romper la API, evitando stock positivo
        accidental.
        """

        payload = self.build_update_variant_payload(producto, include_missing_defaults=True)
        return payload

    def build_update_variant_payload(
        self,
        producto: Producto,
        *,
        include_missing_defaults: bool = False,
    ) -> dict[str, Any]:
        """Payload seguro para variante existente.

        Si `include_missing_defaults=False`, no pisa precio ni stock cuando GBP no
        los informó. Esto evita actualizar un producto existente a precio 0 por
        falta temporal de datos.
        """

        payload: dict[str, Any] = {"sku": str(producto.sku).strip()}

        if producto.precio_importado is not None:
            payload["price"] = self._format_price(producto.precio_importado.monto)
        elif include_missing_defaults:
            payload["price"] = "0.00"

        if producto.stock is not None:
            payload["stock_management"] = True
            payload["stock"] = self._format_stock(producto.stock.cantidad)
        elif include_missing_defaults:
            payload["stock_management"] = True
            payload["stock"] = 0

        # Regla de negocio Silmar: el código de proveedor GBP se publica como
        # barcode en Tienda Nube. No se envía None/"" porque TN puede rechazarlo.
        barcode = normalizar_texto_gbp(producto.codigo_proveedor)
        if barcode:
            payload["barcode"] = barcode

        return payload

    def _build_image_url(self, source_url: str) -> str:
        """Devuelve URL original o URL normalizada pública para Tienda Nube."""

        source_url = source_url.strip()
        if (
            not self.image_normalization_enabled
            or not self.image_normalization_base_url
            or not source_url.lower().startswith(("http://", "https://"))
        ):
            return source_url
        encoded = quote(source_url, safe="")
        size = int(self.image_normalization_canvas_size or 1600)
        return f"{self.image_normalization_base_url}/media/normalized-image?src={encoded}&size={size}"

    @classmethod
    def _format_description_html(cls, value: str | None) -> str:
        """Convierte la descripción GBP en HTML legible para Tienda Nube.

        Tienda Nube renderiza la descripción como HTML. Si se envía texto plano
        con saltos de línea, el navegador colapsa los espacios y la publicación
        queda visualmente apretada. Esta conversión preserva párrafos, viñetas,
        líneas simples y separadores sin permitir HTML crudo no controlado.
        """

        text = normalizar_texto_gbp(value)
        if not text:
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text).strip()

        blocks = re.split(r"\n\s*\n", text)
        html_blocks: list[str] = []
        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            paragraph_lines: list[str] = []
            for line in lines:
                if cls._is_separator_line(line):
                    if paragraph_lines:
                        html_blocks.append("<p>" + "<br>".join(paragraph_lines) + "</p>")
                        paragraph_lines = []
                    html_blocks.append("<hr>")
                    continue
                paragraph_lines.append(html.escape(line, quote=False))

            if paragraph_lines:
                html_blocks.append("<p>" + "<br>".join(paragraph_lines) + "</p>")

        return "\n".join(html_blocks)

    @staticmethod
    def _is_separator_line(value: str) -> bool:
        compact = value.strip()
        return len(compact) >= 8 and len(set(compact)) == 1 and compact[0] in {"=", "-", "_", "*"}

    @staticmethod
    def _format_price(value: Decimal | int | float | str | None) -> str:
        """Formatea precio para Tienda Nube con 2 decimales."""

        if value is None:
            return "0.00"

        try:
            amount = Decimal(str(value)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, ValueError):
            return "0.00"
        return str(amount)

    @staticmethod
    def _format_stock(value: Decimal | int | float | str | None) -> int:
        """Normaliza stock para Tienda Nube como entero no negativo."""

        if value is None:
            return 0
        try:
            return max(0, int(Decimal(str(value))))
        except (InvalidOperation, ValueError):
            return 0

    @staticmethod
    def _build_main_variant(producto: Producto) -> dict[str, Any]:
        """Compatibilidad con tests/uso anterior."""

        return TiendaNubePayloadBuilder().build_create_variant_payload(producto)
