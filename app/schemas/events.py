from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=500)
    product_slug: str | None = Field(default=None, max_length=160)
    occurred_at: datetime | None = None
