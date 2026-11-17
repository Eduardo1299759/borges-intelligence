"""Mensurar: efeito de cada mudança executada, comparando os 7 dias antes e os 7 dias depois.

Antes x depois não prova causa (sazonalidade, concorrência e outras mudanças interferem): o resultado vira um
aprendizado com status "hipótese" e confiabilidade baixa. Só experimentos com teste estatístico validam.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Client, Execution, Recommendation
from app.services.metrics import Totals, compute_kpis, query_totals

WINDOW = 7


def _kpis(db: Session, client: Client, campaign_id: int, start: date, end: date) -> dict[str, Any]:
    t = query_totals(db, client.id, start, end, "campaign_id").get(campaign_id, Totals())
    k = compute_kpis(t, float(client.gross_margin_pct) if client.gross_margin_pct is not None else None)
    return {key: k[key] for key in ("spend", "leads", "confirmed_sales", "cpl", "real_cac", "confirmed_roas")}


def measure(db: Session, client: Client, execution: Execution, last_data_day: date) -> dict[str, Any] | None:
    """None se a janela de 7 dias depois ainda não terminou."""
    rec = db.get(Recommendation, execution.recommendation_id)
    if rec is None or rec.campaign_id is None or execution.finished_at is None:
        return None
    day0 = execution.finished_at.date()
    after_start, after_end = day0 + timedelta(days=1), day0 + timedelta(days=WINDOW)
    if after_end > last_data_day:
        return None
    before = _kpis(db, client, rec.campaign_id, day0 - timedelta(days=WINDOW), day0 - timedelta(days=1))
    after = _kpis(db, client, rec.campaign_id, after_start, after_end)
    metric = "real_cac" if before["real_cac"] is not None and after["real_cac"] is not None else "cpl"

    def change(k: str) -> float | None:
        return (after[k] / before[k] - 1) if before.get(k) and after.get(k) is not None else None
    return {"execution_id": execution.id, "recommendation_id": rec.id, "action": rec.action_type,
            "campaign_id": rec.campaign_id, "campaign": db.get(Campaign, rec.campaign_id).name,
            "before": before, "after": after, "metric": metric, "metric_change": change(metric),
            "spend_change": change("spend"),
            "window": {"before": [str(day0 - timedelta(days=WINDOW)), str(day0 - timedelta(days=1))],
                       "after": [str(after_start), str(after_end)]}}


def pending_executions(db: Session, client: Client) -> list[Execution]:
    return list(db.scalars(select(Execution).where(Execution.client_id == client.id,
                                                   Execution.status == "completed")))
