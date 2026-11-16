"""Cálculo de indicadores. Regras:

- None significa "dado indisponível"; nunca é convertido em zero.
- Divisões por zero/indisponível retornam None.
- Receita atribuída (plataforma) e receita confirmada (CRM/pedidos) nunca são misturadas.
- Receita não é lucro: lucro de contribuição só é calculado quando a margem do cliente foi informada.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MetricDaily, SalesDaily

ADDITIVE = (
    "spend", "impressions", "reach", "clicks", "link_clicks", "leads",
    "attributed_purchases", "attributed_revenue", "confirmed_sales", "confirmed_revenue",
)


@dataclass
class Totals:
    days: int = 0
    spend: float | None = None
    impressions: float | None = None
    reach: float | None = None
    clicks: float | None = None
    link_clicks: float | None = None
    leads: float | None = None
    attributed_purchases: float | None = None
    attributed_revenue: float | None = None
    confirmed_sales: float | None = None
    confirmed_revenue: float | None = None

    def __add__(self, other: Totals) -> Totals:
        out = Totals(days=max(self.days, other.days))
        for name in ADDITIVE:
            a, b = getattr(self, name), getattr(other, name)
            setattr(out, name, None if a is None and b is None else (a or 0) + (b or 0))
        return out


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def query_totals(db: Session, client_id: int, start: date, end: date, group_by: str | None = None) -> dict[Any, Totals]:
    """Soma os fatos do período. group_by: None (conta inteira), 'campaign_id' ou 'date'."""
    m_cols = [func.sum(getattr(MetricDaily, c)) for c in ADDITIVE[:8]]
    m_key = getattr(MetricDaily, group_by) if group_by else None
    s_key = getattr(SalesDaily, group_by) if group_by else None

    mq = select(*([m_key] if group_by else []), func.count(func.distinct(MetricDaily.date)), *m_cols).where(
        MetricDaily.client_id == client_id, MetricDaily.date >= start, MetricDaily.date <= end
    )
    sq = select(
        *([s_key] if group_by else []), func.sum(SalesDaily.confirmed_sales), func.sum(SalesDaily.confirmed_revenue)
    ).where(SalesDaily.client_id == client_id, SalesDaily.date >= start, SalesDaily.date <= end)
    if group_by:
        mq, sq = mq.group_by(m_key), sq.group_by(s_key)

    out: dict[Any, Totals] = {}
    for row in db.execute(mq):
        key, rest = (row[0], row[1:]) if group_by else (None, row)
        if rest[0] == 0:
            continue
        t = Totals(days=rest[0])
        for name, value in zip(ADDITIVE[:8], rest[1:], strict=True):
            setattr(t, name, _f(value))
        out[key] = t
    for row in db.execute(sq):
        key, rest = (row[0], row[1:]) if group_by else (None, row)
        if rest[0] is None:
            continue
        t = out.setdefault(key, Totals())
        t.confirmed_sales, t.confirmed_revenue = _f(rest[0]), _f(rest[1])
    return out


def account_totals(db: Session, client_id: int, start: date, end: date) -> Totals:
    return query_totals(db, client_id, start, end).get(None, Totals())


def compute_kpis(t: Totals, gross_margin_pct: float | None = None) -> dict[str, float | None]:
    margin = None if gross_margin_pct is None else gross_margin_pct / 100
    avg_ticket = div(t.confirmed_revenue, t.confirmed_sales)
    k: dict[str, float | None] = {f.name: getattr(t, f.name) for f in fields(t)}
    k.update(
        ctr=div(t.clicks, t.impressions),
        link_ctr=div(t.link_clicks, t.impressions),
        cpc=div(t.spend, t.clicks),
        cpm=None if div(t.spend, t.impressions) is None else div(t.spend, t.impressions) * 1000,
        # Alcance diário não é deduplicado entre dias: esta é a frequência MÉDIA DIÁRIA, não a do período.
        avg_daily_frequency=div(t.impressions, t.reach),
        cpl=div(t.spend, t.leads),
        attributed_roas=div(t.attributed_revenue, t.spend),
        attributed_cpa=div(t.spend, t.attributed_purchases),
        real_cac=div(t.spend, t.confirmed_sales),
        confirmed_roas=div(t.confirmed_revenue, t.spend),
        lead_to_sale_rate=div(t.confirmed_sales, t.leads),
        avg_ticket=avg_ticket,
        breakeven_roas=div(1.0, margin),
        # CAC máximo na primeira compra (sem LTV, que ainda não é medido).
        max_sustainable_cac=None if margin is None or avg_ticket is None else avg_ticket * margin,
        contribution_profit=(
            None if margin is None or t.confirmed_revenue is None or t.spend is None
            else t.confirmed_revenue * margin - t.spend
        ),
    )
    return k


def previous_period(start: date, end: date) -> tuple[date, date]:
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def data_bounds(db: Session, client_id: int) -> tuple[date | None, date | None]:
    row = db.execute(
        select(func.min(MetricDaily.date), func.max(MetricDaily.date)).where(MetricDaily.client_id == client_id)
    ).one()
    return row[0], row[1]
