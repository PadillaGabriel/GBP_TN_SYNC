from decimal import Decimal, ROUND_HALF_UP
import html
import re
from typing import Any
from urllib.parse import quote

from app.domain.models.producto import Producto
from app.infrastructure.gbp.xml_parser import normalizar_texto_gbp


class TiendaNubePayloadBuilder:
    """Construye payloads de Tienda Nube desde modelos internos."""

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
        """Payload para crear o actualizar producto completo."""

        payload: dict[str, Any] = {
            "name": {"es": normalizar_texto_gbp(producto.titulo)},
            "description": {"es": self._format_description_html(producto.descripcion_web)},
            "variants": [self._build_main_variant(producto)],
        }

        if category_ids:
            payload["categories"] = category_ids

        if producto.imagenes:
            payload["images"] = [
                {"src": self._build_image_url(str(imagen.url))}
                for imagen in sorted(producto.imagenes, key=lambda item: item.orden)
                if imagen.url is not None
            ]

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

        amount = Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return str(amount)

    @staticmethod
    def _build_main_variant(producto: Producto) -> dict[str, Any]:
        precio = (
            TiendaNubePayloadBuilder._format_price(producto.precio_importado.monto)
            if producto.precio_importado
            else "0.00"
        )

        stock = producto.stock.cantidad if producto.stock else 0

        return {
            "sku": producto.sku,
            "price": precio,
            "stock": stock,
            # Regla de negocio Silmar: el codigo de proveedor GBP se publica
            # como codigo universal/barcode en Tienda Nube.
            "barcode": producto.codigo_proveedor,
        }
