from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PUBLIC_FRONTEND_ORIGINS = ("https://hanin.cc", "https://www.hanin.cc")
PUBLIC_TRUSTED_HOSTS = ("api.hanin.cc", "hanin.cc", "www.hanin.cc")


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
    maxmind_minfraud_enabled: bool = False
    maxmind_account_id: str | None = None
    maxmind_license_key: str | None = None
    maxmind_minfraud_service: Literal["score", "insights", "factors"] = "score"
    maxmind_minfraud_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    maxmind_minfraud_host: str = "minfraud.maxmind.com"
    trusted_proxy_ips: str = ""
    # Admin dashboard. Unset username/password disables login (no open admin).
    admin_username: str | None = None
    admin_password: str | None = None
    admin_password_hash: str | None = None
    admin_session_secret: str | None = None
    admin_session_hours: int = Field(default=12, ge=1, le=72)
    admin_login_rate_limit_per_minute: int = Field(default=5, ge=1, le=60)
    ip_hash_secret: str | None = None
    event_rate_limit_per_minute: int = Field(default=60, ge=1, le=600)
    # GeoIP for admin metrics only. Separate from minFraud scoring.
    # Keep MAXMIND_MINFRAUD_ENABLED=false so pageviews do not burn minFraud credits.
    maxmind_geoip_enabled: bool = False
    maxmind_geoip_service: Literal["country", "insights"] = "country"
    maxmind_geoip_timeout_seconds: float = Field(default=3.0, gt=0, le=15)
    maxmind_geolite_country_db: str | None = None
    maxmind_anonymous_ip_db: str | None = None
    # Sandbox mode: when True, order creation still writes to the connected DB
    # but tags the initial status_history entry with `safe_metadata.sandbox=True`
    # so tests can run end-to-end without polluting production semantics. Never
    # enable in production. This intentionally does NOT change the DB schema.
    sandbox_mode: bool = False
    # Optional extra constraint only. City on OrderCreate stays optional and is
    # free text when this list is empty (any reasonable trimmed name or null).
    # Do NOT invent a coverage list. When non-empty, a provided city must match.
    allowed_cities: str = ""

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

    @field_validator("maxmind_minfraud_host")
    @classmethod
    def maxmind_host_allowlist(cls, value: str) -> str:
        allowed = {"minfraud.maxmind.com", "sandbox.maxmind.com"}
        if value not in allowed:
            raise ValueError(
                "MAXMIND_MINFRAUD_HOST must be minfraud.maxmind.com or sandbox.maxmind.com"
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        if self.environment.strip().lower() == "production":
            for origin in PUBLIC_FRONTEND_ORIGINS:
                if origin not in origins:
                    origins.append(origin)
        return origins

    @property
    def trusted_host_list(self) -> list[str]:
        hosts = [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]
        if self.environment.strip().lower() == "production":
            for host in PUBLIC_TRUSTED_HOSTS:
                if host not in hosts:
                    hosts.append(host)
        return hosts

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()]

    @property
    def allowed_city_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_cities.split(",") if item.strip()]

    @property
    def maxmind_account_id_int(self) -> int | None:
        raw = (self.maxmind_account_id or "").strip()
        if not raw.isdigit():
            return None
        return int(raw)

    @property
    def maxmind_license_key_value(self) -> str | None:
        raw = (self.maxmind_license_key or "").strip()
        return raw or None

    @property
    def admin_username_value(self) -> str | None:
        raw = (self.admin_username or "").replace("\ufeff", "").strip()
        return raw or None

    @property
    def admin_password_value(self) -> str | None:
        raw = (self.admin_password or "").replace("\ufeff", "").strip()
        return raw or None

    @property
    def admin_password_hash_value(self) -> str | None:
        raw = (self.admin_password_hash or "").replace("\ufeff", "").strip().lower()
        return raw or None

    @property
    def admin_session_secret_value(self) -> str | None:
        raw = (self.admin_session_secret or "").strip()
        return raw or None

    @property
    def ip_hash_secret_value(self) -> str | None:
        raw = (self.ip_hash_secret or "").strip()
        return raw or self.admin_session_secret_value

    @property
    def geolite_country_db_path(self) -> str | None:
        raw = (self.maxmind_geolite_country_db or "").strip()
        return raw or None

    @property
    def anonymous_ip_db_path(self) -> str | None:
        raw = (self.maxmind_anonymous_ip_db or "").strip()
        return raw or None

    def admin_is_configured(self) -> bool:
        if not self.admin_username_value:
            return False
        return bool(self.admin_password_value or self.admin_password_hash_value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
