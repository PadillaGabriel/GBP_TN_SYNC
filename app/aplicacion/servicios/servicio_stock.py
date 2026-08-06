from app.dominio.modelos.stock import StockDeposito, StockProducto


class StockService:
    """Calcula stock disponible publicable para Tienda Nube."""

    def calcular_stock_publicable(
        self,
        *,
        sku: str,
        id_sistema_gbp: str,
        depositos: list[StockDeposito],
        depositos_habilitados: list[str],
    ) -> StockProducto:
        """Suma solo el campo Stock de depositos habilitados para ecommerce."""

        habilitados = set(depositos_habilitados)
        stock_total = 0.0
        depositos_resultado: list[StockDeposito] = []

        for deposito in depositos:
            usado = deposito.stor_id in habilitados if habilitados else False
            stock_disponible = deposito.stock_disponible
            if usado:
                stock_total += stock_disponible
            depositos_resultado.append(
                deposito.model_copy(update={"usado_para_tienda_nube": usado})
            )

        stock_tn = max(0, int(stock_total))
        return StockProducto(
            sku=sku,
            id_sistema_gbp=id_sistema_gbp,
            cantidad=stock_tn,
            stock_original_gbp=stock_total,
            depositos=depositos_resultado,
        )
