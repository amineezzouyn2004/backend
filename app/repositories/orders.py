from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.order import IdempotencyRecord, Order


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_idempotency(self, scope: str, key: str) -> IdempotencyRecord | None:
        return self.db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
        )

    def find_by_public_reference(self, reference: str) -> Order | None:
        return self.db.scalar(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.status_history))
            .where(Order.public_reference == reference)
        )
