"""Visão geral e gestor de campanhas (somente leitura)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import data_intelligence, financial
from app.api.deps import current_user
from app.api.serializers import recommendation_out
from app.core.db import get_db
from app.models import (
    REC_ADJUST,
    REC_AWAITING,
    Ad,
    AdSet,
    BreakdownDaily,
    Campaign,
    Client,
    Execution,
    Recommendation,
    User,
)
from app.services.access import get_client_or_404
from app.services.metrics import (
    Totals,
    account_totals,
    compute_kpis,
    data_bounds,
    pct_change,
    previous_period,
    query_totals,
)

router = APIRouter(prefix="/clients/{client_id}", tags=["insights"])

COMPARED = ("spend", "leads", "confirmed_sales", "confirmed_revenue", "real_cac", "confirmed_roas", "cpl", "ctr",
            "contribution_profit", "attributed_revenue", "lead_to_sale_rate")


def resolve_period(db: Session, client: Client, days: int) -> tuple[date, date]:
    """O período termina no último dia com dados; sem dados, termina ontem."""
    _, last = data_bounds(db, client.id)
    end = last or (date.today() - timedelta(days=1))
    return end - timedelta(days=days - 1), end


@router.get("/dashboard")
def dashboard(client_id: int, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    margin = float(client.gross_margin_pct) if client.gross_margin_pct is not None else None
    start, end = resolve_period(db, client, days)
    p_start, p_end = previous_period(start, end)
    current = compute_kpis(account_totals(db, client.id, start, end), margin)
    previous = compute_kpis(account_totals(db, client.id, p_start, p_end), margin)
    by_day = query_totals(db, client.id, start, end, "date")
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        t = by_day.get(d)
        series.append({"date": d.isoformat(), "spend": t.spend if t else None,
                       "confirmed_revenue": t.confirmed_revenue if t else None,
                       "leads": t.leads if t else None, "confirmed_sales": t.confirmed_sales if t else None})
    alerts = db.scalars(
        select(Recommendation).where(Recommendation.client_id == client.id,
                                     Recommendation.status.in_([REC_AWAITING, REC_ADJUST]))
        .order_by(Recommendation.priority_score.desc()).limit(5)).all()
    quality = data_intelligence.validate(db, client, start, end)
    return {
        "client_id": client.id,
        "is_demo": client.data_mode == "demo",
        "has_data": quality["has_data"],
        "currency": client.currency,
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "previous_period": {"start": p_start.isoformat(), "end": p_end.isoformat()},
        "kpis": current,
        "previous_kpis": previous,
        "changes": {k: pct_change(current[k], previous[k]) for k in COMPARED},
        "targets": {"cac": float(client.target_cac) if client.target_cac is not None else None,
                    "roas": float(client.target_roas) if client.target_roas is not None else None},
        "pacing": financial.pacing(
            account_totals(db, client.id, end.replace(day=1), end).spend if quality["has_data"] else None,
            float(client.monthly_budget) if client.monthly_budget is not None else None, end),
        "series": series,
        "alerts": [recommendation_out(r) for r in alerts],
        "data_quality": quality,
    }


@router.get("/campaigns")
def campaigns(client_id: int, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    margin = float(client.gross_margin_pct) if client.gross_margin_pct is not None else None
    start, end = resolve_period(db, client, days)
    totals = query_totals(db, client.id, start, end, "campaign_id")
    changes: dict[int, list[dict]] = {}
    for ex, rec in db.execute(
        select(Execution, Recommendation).join(Recommendation, Execution.recommendation_id == Recommendation.id)
        .where(Execution.client_id == client.id).order_by(Execution.id.desc())
    ):
        changes.setdefault(rec.campaign_id, []).append({
            "execution_id": ex.id, "status": ex.status, "mode": ex.mode, "verified": ex.verified,
            "before": ex.before_state, "after": ex.after_state, "title": rec.title,
            "finished_at": ex.finished_at.isoformat() if ex.finished_at else None,
        })
    rows = []
    campaign_q = select(Campaign).where(Campaign.client_id == client.id).order_by(Campaign.platform, Campaign.name)
    for c in db.scalars(campaign_q):
        t = totals.get(c.id)
        rows.append({
            "id": c.id, "name": c.name, "platform": c.platform, "objective": c.objective, "status": c.status,
            "daily_budget": float(c.daily_budget) if c.daily_budget is not None else None, "is_demo": c.is_demo,
            "kpis": compute_kpis(t, margin) if t else None,
            "changes": changes.get(c.id, []),
        })
    return {"is_demo": client.data_mode == "demo", "currency": client.currency,
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days}, "campaigns": rows}


@router.get("/campaigns/{campaign_id}/breakdown")
def campaign_breakdown(client_id: int, campaign_id: int, days: int = Query(30, ge=7, le=90),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Conjuntos/grupos e anúncios de uma campanha, com os indicadores que a fonte entrega nesse nível."""
    client = get_client_or_404(db, user, client_id)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.client_id != client.id:
        raise HTTPException(404, "Campanha não encontrada.")
    start, end = resolve_period(db, client, days)
    cols = ("spend", "impressions", "clicks", "link_clicks", "leads", "attributed_purchases", "attributed_revenue")
    rows = db.execute(
        select(BreakdownDaily.ad_set_id, BreakdownDaily.ad_id, *[func.sum(getattr(BreakdownDaily, c)) for c in cols])
        .where(BreakdownDaily.client_id == client.id, BreakdownDaily.campaign_id == campaign.id,
               BreakdownDaily.date >= start, BreakdownDaily.date <= end)
        .group_by(BreakdownDaily.ad_set_id, BreakdownDaily.ad_id)
    ).all()

    def kpis(values: dict[str, float | None]) -> dict[str, float | None]:
        t = Totals(days=0, **values)
        k = compute_kpis(t)
        return {key: k[key] for key in (*cols, "ctr", "cpc", "cpl", "attributed_roas")}

    names = {a.id: a for a in db.scalars(select(Ad).where(Ad.campaign_id == campaign.id))}
    out = []
    for ad_set in db.scalars(select(AdSet).where(AdSet.campaign_id == campaign.id).order_by(AdSet.name)):
        mine = [r for r in rows if r[0] == ad_set.id]
        if not mine:
            continue
        total = Totals()
        ads = []
        for r in mine:
            values = {c: (float(v) if v is not None else None) for c, v in zip(cols, r[2:], strict=True)}
            total = total + Totals(**values)
            if r[1] is not None:
                ads.append({"id": r[1], "name": names[r[1]].name, "kpis": kpis(values)})
        ads.sort(key=lambda a: a["kpis"]["spend"] or 0, reverse=True)
        out.append({"id": ad_set.id, "name": ad_set.name,
                    "kpis": kpis({c: getattr(total, c) for c in cols}), "ads": ads})
    out.sort(key=lambda s: s["kpis"]["spend"] or 0, reverse=True)
    return {"campaign_id": campaign.id, "platform": campaign.platform,
            "period": {"start": start.isoformat(), "end": end.isoformat()}, "ad_sets": out}
