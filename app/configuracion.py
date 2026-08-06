from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfiguracionAplicacion(BaseSettings):
    """Configuracion central de la aplicacion.

    Todas las decisiones operativas del integrador se controlan por variables de
    entorno para que Render pueda ejecutar el mismo repositorio en produccion.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Integrador GBP TN"
    app_env: str = "local"
    app_debug: bool = False
    app_public_base_url: str = ""
    database_url: str = "sqlite+pysqlite:///./integrador_gbp_tn.db"

    gbp_base_url: str = Field(
        default=(
            "http://ws.globalbluepoint.com/silmarbazar/"
            "app_webservices/wsBasicQuery.asmx"
        )
    )
    gbp_username: str = ""
    gbp_password: str = ""
    gbp_company_id: str = ""
    gbp_web_service_id: str = ""
    gbp_timeout_seconds: int = 20
    gbp_retry_attempts: int = 2
    gbp_module16_strict: bool = True

    gbp_export_producto_por_item_id: int = 11
    gbp_export_productos_general_id: int = 12
    gbp_export_productos_precios_id: int = 13
    gbp_export_productos_stock_id: int = 14
    gbp_export_cache_seconds: int = 120

    tienda_nube_store_id: str = ""
    tienda_nube_access_token: str = ""
    tienda_nube_base_url: str = "https://api.tiendanube.com/v1"
    tienda_nube_timeout_seconds: int = 20
    tienda_nube_user_agent: str = "IntegradorGBP-TN/1.0"
    tienda_nube_webhook_secret: str = ""
    tienda_nube_webhook_events: str = "order/paid"
    tienda_nube_pedidos_automaticos_habilitados: bool = False

    image_normalization_enabled: bool = False
    image_normalization_canvas_size: int = 1600

    online_price_list_id: int = 4
    ecommerce_storage_ids: str = "18"

    stock_scheduler_enabled: bool = False
    stock_sync_interval_minutes: int = 10
    stock_sync_batch_size: int = 50
    stock_sync_concurrency: int = 5

    import_scheduler_enabled: bool = False
    product_audit_interval_hours: int = 24

    dry_run: bool = True
    pedidos_escritura_gbp_habilitada: bool = False

    pedidos_gbp_company_id: int = 1
    pedidos_gbp_branch_id: int = 28
    pedidos_gbp_profile_id: int = 1
    pedidos_gbp_storage_id: int = 18
    pedidos_gbp_price_list_id: int = 4
    pedidos_gbp_salesman_id: int = 10
    pedidos_gbp_sales_terms_id: int = 20
    pedidos_gbp_currency_id: int = 1
    pedidos_gbp_order_type_id: int = 1
    pedidos_gbp_transaction_id: int = 1
    pedidos_gbp_transaction_class: str = "A"
    pedidos_gbp_initial_status_id: int = 50
    pedidos_gbp_invoice_a_document_id: int = 98
    pedidos_gbp_invoice_b_document_id: int = 145
    pedidos_gbp_customer_country_id: int = 54
    pedidos_gbp_customer_fiscal_class_id: int = 2
    pedidos_gbp_sale_order_base_url: str = (
        "http://ws.globalbluepoint.com/silmarbazar/" "app_webservices/wsSaleOrder.asmx"
    )
    pedidos_gbp_language_id: int = 2
    pedidos_gbp_delivery_id: int = 1
    pedidos_gbp_discount_id: int = 1
    pedidos_gbp_shipping_item_id: int = 7774
    pedidos_gbp_shipping_special_qty: Decimal = Decimal("1")
    pedidos_gbp_discount_item_code: str = "CUPON"
    pedidos_gbp_discount_special_qty: Decimal = Decimal("-1")
    pedidos_gbp_staging_enabled: bool = False
    pedidos_gbp_confirmation_enabled: bool = False
    pedidos_gbp_total_tolerance: Decimal = Decimal("0.01")
    pedidos_gbp_residual_maximo_ajustable: Decimal = Decimal("0.05")
    pedidos_gbp_prices_include_vat: bool = True
    pedidos_gbp_default_vat_rate: Decimal = Decimal("21")
    pedidos_gbp_vat_rate_overrides: str = ""
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Adapta URL de Railway/Render al driver de SQLAlchemy 2.

        Railway suele entregar DATABASE_URL como postgresql://. La aplicacion usa
        psycopg, por eso se normaliza a postgresql+psycopg://.
        """

        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def tienda_nube_webhook_event_list(self) -> list[str]:
        """Eventos de pedidos autorizados para procesamiento automático."""

        return [
            event.strip().lower()
            for event in self.tienda_nube_webhook_events.split(",")
            if event.strip()
        ]

    @property
    def ecommerce_storage_id_list(self) -> list[str]:
        """Devuelve depositos habilitados para stock publicable."""

        return [
            item.strip()
            for item in self.ecommerce_storage_ids.split(",")
            if item.strip()
        ]

    @property
    def ecommerce_primary_storage_id(self) -> int:
        """Devuelve el primer deposito ecommerce configurado para consultas puntuales.

        Si no hay deposito configurado o no puede convertirse a entero, usa -1
        para consultar todos los depositos disponibles en GBP.
        """

        for item in self.ecommerce_storage_id_list:
            try:
                return int(str(item).strip())
            except (TypeError, ValueError):
                continue
        return -1


@lru_cache
def obtener_configuracion() -> ConfiguracionAplicacion:
    """Devuelve configuracion cacheada para toda la aplicacion."""

    return ConfiguracionAplicacion()
