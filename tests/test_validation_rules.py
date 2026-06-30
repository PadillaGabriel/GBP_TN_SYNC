from decimal import Decimal

from app.application.services.producto_validation_service import ProductoValidationService
from app.domain.models.imagen import ImagenProducto
from app.domain.models.precio import PrecioProducto
from app.domain.models.producto import Producto
from app.domain.models.stock import StockDeposito, StockProducto


def _producto_base(stock_cantidad: int) -> Producto:
    return Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        publicable_web=True,
        descripcion_web="Descripcion web",
        precio_importado=PrecioProducto(monto=Decimal("100.00"), lista_precio_id="1"),
        imagenes=[ImagenProducto(url="https://example.com/imagen.jpg", orden=1)],
        stock=StockProducto(
            sku="SKU1",
            id_sistema_gbp="1",
            cantidad=max(0, stock_cantidad),
            stock_original_gbp=float(stock_cantidad),
            depositos=[
                StockDeposito(
                    stor_id="18",
                    stock_disponible=max(0, stock_cantidad),
                    stock_original=float(stock_cantidad),
                    usado_para_tienda_nube=True,
                )
            ],
        ),
    )


def test_stock_cero_bloquea_publicacion_automatica() -> None:
    resultado = ProductoValidationService().validar_publicacion(_producto_base(0))

    assert resultado.publicable is False
    assert resultado.decision == "NO_PUBLICAR_STOCK_SIN_DISPONIBLE"
    assert "STOCK_SIN_DISPONIBLE" in resultado.motivos_bloqueo


def test_item_web_false_y_no_confirmado_tienen_motivos_diferentes() -> None:
    producto_false = _producto_base(5)
    producto_false.publicable_web = False

    producto_none = _producto_base(5)
    producto_none.publicable_web = None

    assert "ITEM_WEB_FALSE" in ProductoValidationService().validar_publicacion(
        producto_false
    ).motivos_bloqueo
    assert "ITEM_WEB_NO_CONFIRMADO" in ProductoValidationService().validar_publicacion(
        producto_none
    ).motivos_bloqueo


def test_manual_flexible_no_bloquea_por_datos_web_operativos_faltantes() -> None:
    producto = Producto(
        sku="536HUELLAS",
        id_sistema_gbp="13170",
        titulo="536HUELLAS",
        publicable_web=None,
        descripcion_web="536HUELLAS",
        precio_importado=None,
        imagenes=[],
        stock=None,
    )

    resultado = ProductoValidationService().validar_publicacion(
        producto,
        exigir_item_web=False,
        modo_manual_flexible=True,
    )

    assert resultado.publicable is True
    assert resultado.decision == "PUBLICABLE_AUTOMATICO"
    assert resultado.motivos_bloqueo == []
    assert "item_web omitido por importacion manual" in resultado.cumple
    assert "Precio online omitido por importacion manual" in resultado.cumple
    assert "Stock omitido por importacion manual" in resultado.cumple


def test_manual_flexible_permite_stock_cero_si_es_consultable() -> None:
    producto = _producto_base(0)
    producto.publicable_web = None

    resultado = ProductoValidationService().validar_publicacion(
        producto,
        exigir_item_web=False,
        modo_manual_flexible=True,
    )

    assert resultado.publicable is True
    assert "STOCK_SIN_DISPONIBLE" not in resultado.motivos_bloqueo
    assert "Stock 0 permitido por importacion manual" in resultado.cumple
