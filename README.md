# Hanin backend

FastAPI foundation مع SQLAlchemy sync وPostgreSQL وطلبات `pending`
idempotent. صورة API تشغّل Uvicorn فقط؛ لا Alembic ولا ترحيلات عند الإقلاع.

```powershell
uv sync --frozen
$env:DATABASE_URL = "postgresql+psycopg://hanin:hanin_dev_only@localhost:5432/hanin"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

المخطط يُدار خارج هذه الخدمة (عمليات/قاعدة، وليس من صورة الـAPI). الاختبارات
تنشئ الجداول عبر `SQLAlchemy metadata.create_all` محليًا فقط.

```powershell
uv run pytest
```

التتبع no-op ومعطّل افتراضيًا. لا تُرسل أسعار من العميل؛ backend يحسب قيمة
العرض من الإعداد المركزي.
