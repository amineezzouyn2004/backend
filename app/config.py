from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    database_url: str
    cors_origins: str = "http://localhost:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    openapi_enabled: bool = True
    demo_offer_mapping_enabled: bool = False
    upsell_enabled: bool = False
    upsell_product_slug: str | None = None
    tracking_enabled: bool = False
    purchase_tracking_enabled: bool = False
    rate_limit_enabled: bool = False
    order_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    max_request_body_bytes: int = Field(default=32_768, ge=1024, le=1_048_576)
    sheets_webhook_enabled: bool = False
    sheets_webhook_url: str | None = None
    sheets_webhook_secret: str | None = None
    sheets_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    outbox_poll_seconds: float = Field(default=5.0, ge=1, le=60)
    outbox_max_attempts: int = Field(default=8, ge=1, le=30)
    meta_capi_enabled: bool = False
    meta_capi_endpoint: str | None = None
    meta_access_token: str | None = None
    tiktok_capi_enabled: bool = False
    tiktok_capi_endpoint: str | None = None
    tiktok_access_token: str | None = None
    snap_capi_enabled: bool = False
    snap_pixel_id: str | None = None
    snap_access_token: str | None = None

    @model_validator(mode="after")
    def validate_feature_configuration(self) -> "Settings":
        if self.upsell_enabled and not self.upsell_product_slug:
            raise ValueError("UPSELL_PRODUCT_SLUG is required when UPSELL_ENABLED=true")
        if self.sheets_webhook_enabled and (
            not self.sheets_webhook_url or not self.sheets_webhook_secret
        ):
            raise ValueError(
                "SHEETS_WEBHOOK_URL and SHEETS_WEBHOOK_SECRET are required when enabled"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
