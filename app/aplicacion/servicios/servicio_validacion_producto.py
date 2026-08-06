from pydantic import BaseModel, Field

from app.dominio.decisiones_producto import (
    PUBLICABLE_AUTOMATICO,
    PUBLICABLE_CONSULTAR_PRECIO,
)
from app.dominio.modelos.producto import Producto


class ResultadoValidacionProducto(BaseModel):
    """Resultado explicable de publicabilidad."""

    decision: str
    publicable: bool
    motivos_bloqueo: list[str] = Field(default_factory=list)
    cumple: list[str] = Field(default_factory=list)


class ProductoValidationService:
    """Evalúa si un producto GBP puede publicarse de forma controlada."""

    def validar_publicacion(
        self,
        producto: Producto,
        *,
        exigir_item_web: bool = True,
        modo_manual_flexible: bool = False,
    ) -> ResultadoValidacionProducto:
        motivos: list[str] = []
        cumple: list[str] = []

        self._check(bool(producto.sku.strip()), "SKU válido", "SIN_SKU", motivos, cumple)
        self._check(
            bool(producto.titulo.strip()), "Título válido", "SIN_TITULO", motivos, cumple
        )
        if modo_manual_flexible and not producto.tiene_imagen_website:
            cumple.append("Imagen Website omitida por importación manual")
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
            cumple.append("item_web omitido por importación manual")

        self._check(
            not producto.item_disabled,
            "item_disabled=false",
            "ITEM_DISABLED",
            motivos,
            cumple,
        )
        self._check(
            not producto.item_not_for_sale,
            "item_not4Sale=false",
            "ITEM_NOT_FOR_SALE",
            motivos,
            cumple,
        )

        if modo_manual_flexible and not producto.tiene_descripcion_web:
            cumple.append("Descripción Website omitida por importación manual")
        else:
            self._check(
                producto.tiene_descripcion_web,
                "Descripción Website",
                "SIN_DESCRIPCION_WEB",
                motivos,
                cumple,
            )

        # La ausencia de fila en la exportación 13 es un error técnico. Un precio
        # explícito igual a cero sí es publicable como "Consultar precio".
        if producto.precio_importado is None:
            motivos.append("PRECIO_NO_ENCONTRADO")
        elif producto.precio_importado.monto < 0:
            motivos.append("PRECIO_NEGATIVO")
        elif producto.requiere_consultar_precio:
            cumple.append("Precio 0 informado: publicar como Consultar precio")
        else:
            cumple.append("Precio online válido")

        # Stock cero es válido y debe enviarse. Solo se bloquea cuando la fuente
        # de stock no existe o no es consultable.
        self._check(
            producto.stock is not None and producto.stock.consultable,
            "Stock disponible consultable",
            "STOCK_NO_CONSULTABLE",
            motivos,
            cumple,
        )
        if producto.stock is not None and producto.stock.consultable:
            if producto.stock.cantidad > 0:
                cumple.append("Stock mayor a 0")
            else:
                cumple.append("Stock 0 permitido")

        if motivos:
            return ResultadoValidacionProducto(
                decision=self._decision_por_motivo(motivos[0]),
                publicable=False,
                motivos_bloqueo=motivos,
                cumple=cumple,
            )

        decision = (
            PUBLICABLE_CONSULTAR_PRECIO
            if producto.requiere_consultar_precio
            else PUBLICABLE_AUTOMATICO
        )
        return ResultadoValidacionProducto(
            decision=decision,
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
