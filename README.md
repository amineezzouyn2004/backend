# Hanin backend

FastAPI foundation مع SQLAlchemy sync، PostgreSQL، Alembic، وطلبات `pending`
idempotent. لا توجد ترحيلات تلقائية عند بدء API.

```powershell
uv sync --frozen
$env:DATABASE_URL = "postgresql+psycopg://hanin:hanin_dev_only@localhost:5432/hanin"
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
uv run pytest
uv run alembic check
```

التتبع no-op ومعطّل افتراضيًا. لا تُرسل أسعار من العميل؛ backend يحسب قيمة
العرض من الإعداد المركزي.
