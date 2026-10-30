import os

import pytest

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CORS_ORIGINS"] = "http://testserver"
os.environ["TRUSTED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["DEMO_OFFER_MAPPING_ENABLED"] = "true"
os.environ["UPSELL_ENABLED"] = "false"
os.environ["TRACKING_ENABLED"] = "false"
os.environ["PURCHASE_TRACKING_ENABLED"] = "false"
os.environ["SHEETS_WEBHOOK_ENABLED"] = "false"
os.environ["META_CAPI_ENABLED"] = "false"
os.environ["TIKTOK_CAPI_ENABLED"] = "false"
os.environ["SNAP_CAPI_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["MAXMIND_MINFRAUD_ENABLED"] = "false"
os.environ["MAXMIND_ACCOUNT_ID"] = ""
os.environ["MAXMIND_LICENSE_KEY"] = ""

from app.middleware import reset_rate_limit_state


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()
