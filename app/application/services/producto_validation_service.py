from pydantic import BaseModel, Field

from app.domain.models.producto import Producto


class ResultadoValidacionProducto(BaseModel):
    """Resultado explicable de publicabilidad."""

    decision: str
    publicable: bool
    motivos_bloqueo: list[str] = Field(default_factory=list)
    cumple: list[str] = Field(default_factory=list)


class ProductoValidationService:
    """Evalua si un producto GBP puede publicarse automaticamente."""

    def validar_publicacion(
        self,
        producto: Producto,
        *,
        exigir_item_web: bool = True,
        modo_manual_flexible: bool = False,
    ) -> ResultadoValidacionProducto:
        motivos: list[str] = []
        cumple: list[str] = []

        self._check(bool(producto.sku.strip()), "SKU valido", "SIN_SKU", motivos, cumple)
        self._check(bool(producto.titulo.strip()), "Titulo valido", "SIN_TITULO", motivos, cumple)
        if modo_manual_flexible and not producto.tiene_imagen_website:
            cumple.append("Imagen Website omitida por importacion manual")
        else:
            self._check(
                producto.tiene_imagen_website,
                "Imagen Website",
                "SIN_IMAGEN_WEBSITE",
                motivos,
                cumple,
            )
        if producto.publicable_web is True:
            cumple.append("item_web=true")
        elif exigir_item_web and producto.publicable_web is False:
            motivos.append("ITEM_WEB_FALSE")
        elif exigir_item_web and producto.publicable_web is None:
            motivos.append("ITEM_WEB_NO_CONFIRMADO")
        else:
            cumple.append("item_web omitido por importacion manual")
            
        self._check(not producto.item_disabled, "item_disabled=false", "ITEM_DISABLED", motivos, cumple)
        self._check(not producto.item_not_for_sale, "item_not4Sale=false", "ITEM_NOT_FOR_SALE", motivos, cumple)
        if modo_manual_flexible and not producto.tiene_descripcion_web:
            cumple.append("Descripcion Website omitida por importacion manual")
        else:
            self._check(
                producto.tiene_descripcion_web,
                "Descripcion Website",
                "SIN_DESCRIPCION_WEB",
                motivos,
                cumple,
            )
        if modo_manual_flexible and not producto.precio_online_valido:
            cumple.append("Precio online omitido por importacion manual")
        else:
            self._check(
                producto.precio_online_valido,
                "Precio online valido",
                "SIN_PRECIO_ONLINE",
                motivos,
                cumple,
            )
        if modo_manual_flexible and producto.stock is None:
            cumple.append("Stock omitido por importacion manual")
        else:
            self._check(
                producto.stock is not None and producto.stock.consultable,
                "Stock disponible consultable",
                "STOCK_NO_CONSULTABLE",
                motivos,
                cumple,
            )
            self._check(
                producto.stock is not None and producto.stock.cantidad > 0,
                "Stock mayor a 0",
                "STOCK_SIN_DISPONIBLE",
                motivos,
                cumple,
            )

        if motivos:
            return ResultadoValidacionProducto(
                decision=self._decision_por_motivo(motivos[0]),
                publicable=False,
                motivos_bloqueo=motivos,
                cumple=cumple,
            )

        return ResultadoValidacionProducto(
            decision="PUBLICABLE_AUTOMATICO",
            publicable=True,
            cumple=cumple,
        )

    @staticmethod
    def _check(
        condition: bool,
        ok_label: str,
        fail_code: str,
        motivos: list[str],
        cumple: list[str],
    ) -> None:
        if condition:
            cumple.append(ok_label)
        else:
            motivos.append(fail_code)

    @staticmethod
    def _decision_por_motivo(motivo: str) -> str:
        if motivo.startswith("ERROR_"):
            return motivo
        return f"NO_PUBLICAR_{motivo}"
