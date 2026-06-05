from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
        default="http://ws.globalbluepoint.com/silmarbazar/app_webservices/wsBasicQuery.asmx"
    )
    gbp_username: str = ""
    gbp_password: str = ""
    gbp_company_id: str = ""
    gbp_web_service_id: str = ""
    gbp_timeout_seconds: int = 20
    gbp_retry_attempts: int = 2
    gbp_module16_strict: bool = True

    tienda_nube_store_id: str = ""
    tienda_nube_access_token: str = ""
    tienda_nube_base_url: str = "https://api.tiendanube.com/v1"
    tienda_nube_timeout_seconds: int = 20
    tienda_nube_user_agent: str = "IntegradorGBP-TN/1.0"

    online_price_list_id: int = 1
    ecommerce_storage_ids: str = ""

    stock_scheduler_enabled: bool = False
    stock_sync_interval_minutes: int = 10
    stock_sync_batch_size: int = 50
    stock_sync_concurrency: int = 5

    import_scheduler_enabled: bool = False
    product_audit_interval_hours: int = 24

    dry_run: bool = True
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
    def ecommerce_storage_id_list(self) -> list[str]:
        """Devuelve depositos habilitados para stock publicable."""

        return [item.strip() for item in self.ecommerce_storage_ids.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve configuracion cacheada para toda la aplicacion."""

    return Settings()
