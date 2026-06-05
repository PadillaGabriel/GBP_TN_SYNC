from pydantic import BaseModel, Field


class StockDeposito(BaseModel):
    """Stock devuelto por GBP para un deposito."""

    stor_id: str
    stock_disponible: int
    stock_original: float
    usado_para_tienda_nube: bool = False


class StockProducto(BaseModel):
    """Stock normalizado para Tienda Nube.

    El stock publicable usa el campo Stock de GBP, no el stock fisico general.
    """

    sku: str
    cantidad: int
    id_sistema_gbp: str | None = None
    stock_original_gbp: float | None = None
    depositos: list[StockDeposito] = Field(default_factory=list)

    @property
    def consultable(self) -> bool:
        """El stock es consultable si hay al menos un deposito informado."""

        return any(deposito.usado_para_tienda_nube for deposito in self.depositos)
