from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AISettings, AIUsage


def get_settings_row(db: Session) -> AISettings:
    row = db.get(AISettings, 1)
    if row is None:
        row = AISettings(id=1)
        db.add(row)
        db.flush()
    return row


def month_spend(db: Session, now: datetime | None = None) -> Decimal:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(select(func.sum(AIUsage.cost_usd)).where(AIUsage.created_at >= start))
    return Decimal(total or 0)
