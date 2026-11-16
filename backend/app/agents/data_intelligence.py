"""Agente 01 — Data Intelligence (Fase 1: validação do que está armazenado)."""
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdAccount, Campaign, Client, MetricDaily, SalesDaily


def validate(db: Session, client: Client, start: date, end: date) -> dict[str, Any]:
    expected = (end - start).days + 1
    rows = db.execute(
        select(Campaign.id, Campaign.name, func.count(func.distinct(MetricDaily.date)), func.min(MetricDaily.date))
        .join(MetricDaily, MetricDaily.campaign_id == Campaign.id)
        .where(Campaign.client_id == client.id, MetricDaily.date >= start, MetricDaily.date <= end)
        .group_by(Campaign.id, Campaign.name)
    ).all()
    issues: list[str] = []
    coverage = []
    for cid, name, days, first in rows:
        # Lacuna = dias faltando DEPOIS do primeiro dia com dados (campanha nova não é lacuna).
        gaps = ((end - max(first, start)).days + 1) - days
        coverage.append({"campaign_id": cid, "name": name, "days_with_data": days, "missing_days": gaps})
        if gaps > 0:
            issues.append(f"“{name}” tem {gaps} dia(s) sem dados no período.")
    sources = sorted(set(db.scalars(select(MetricDaily.source).where(MetricDaily.client_id == client.id).distinct()))
                     | set(db.scalars(select(SalesDaily.source).where(SalesDaily.client_id == client.id).distinct())))
    has_sales = db.scalar(select(func.count()).select_from(SalesDaily).where(
        SalesDaily.client_id == client.id, SalesDaily.date >= start, SalesDaily.date <= end)) or 0
    if rows and not has_sales:
        issues.append("Não há vendas confirmadas no período: CAC real e ROAS confirmado ficam indisponíveis.")
    last_sync = db.scalar(select(func.max(AdAccount.last_synced_at)).where(AdAccount.client_id == client.id))
    return {
        "has_data": bool(rows),
        "is_demo": client.data_mode == "demo",
        "sources": sources,
        "expected_days": expected,
        "coverage": coverage,
        "issues": issues,
        "last_synced_at": last_sync.isoformat() if last_sync else None,
    }
