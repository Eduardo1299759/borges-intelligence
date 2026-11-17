"""Agente 10 — Experimentation Engine: planejamento, avaliação e conclusão de testes entre anúncios."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.experiments.stats import Arm, evaluate
from app.models import Ad, BreakdownDaily, Client, Experiment, MetricDaily

METRIC_LABEL = {"lead_rate": "Taxa clique → lead", "cpl": "Custo por lead"}


def validate_ads(db: Session, client: Client, control: list[int], variant: list[int]) -> int:
    """Confere que os anúncios existem, são do cliente, da mesma campanha e não se repetem. Retorna a campanha."""
    if not control or not variant:
        raise HTTPException(422, "Escolha ao menos um anúncio de controle e um de variante.")
    if set(control) & set(variant):
        raise HTTPException(422, "Um anúncio não pode estar no controle e na variante ao mesmo tempo.")
    ads = db.scalars(select(Ad).where(Ad.id.in_(control + variant))).all()
    if len(ads) != len(set(control + variant)) or any(a.client_id != client.id for a in ads):
        raise HTTPException(404, "Anúncio não encontrado.")
    campaigns = {a.campaign_id for a in ads}
    if len(campaigns) != 1:
        raise HTTPException(422, "Controle e variante precisam ser anúncios da mesma campanha.")
    return campaigns.pop()


def _arm(db: Session, client: Client, ad_ids: list[int], start: date, end: date) -> Arm:
    row = db.execute(
        select(func.sum(BreakdownDaily.spend), func.sum(BreakdownDaily.impressions),
               func.sum(BreakdownDaily.clicks), func.sum(BreakdownDaily.leads))
        .where(BreakdownDaily.client_id == client.id, BreakdownDaily.ad_id.in_(ad_ids),
               BreakdownDaily.date >= start, BreakdownDaily.date <= end)
    ).one()
    return Arm(*(float(v or 0) for v in row))


def _arm_out(arm: Arm) -> dict[str, Any]:
    return {"spend": arm.spend, "impressions": arm.impressions, "clicks": arm.clicks, "leads": arm.leads,
            "lead_rate": arm.rate, "cpl": arm.cpl, "cpc": arm.cpc, "ctr": arm.ctr}


def last_data_day(db: Session, client: Client) -> date:
    last = db.scalar(select(func.max(MetricDaily.date)).where(MetricDaily.client_id == client.id))
    return last or (date.today() - timedelta(days=1))


def evaluation(db: Session, client: Client, exp: Experiment) -> dict[str, Any] | None:
    """Resultado parcial ou final no período do teste. None se o teste ainda não começou."""
    if exp.start_date is None:
        return None
    planned_end = exp.start_date + timedelta(days=exp.planned_days - 1)
    end = min(planned_end, last_data_day(db, client))
    if end < exp.start_date:
        return {"window": {"start": exp.start_date, "end": None, "days_with_data": 0, "planned_end": planned_end},
                "verdict": {"status": "waiting_volume", "label": "Aguardando os primeiros dados"}}
    control = _arm(db, client, exp.control_ad_ids, exp.start_date, end)
    variant = _arm(db, client, exp.variant_ad_ids, exp.start_date, end)
    v = evaluate(control, variant, float(exp.relative_mde_pct) / 100, duration_reached=end >= planned_end)
    days = (end - exp.start_date).days + 1
    remaining = None
    if v.status in ("waiting_volume", "trending_better", "trending_worse") and v.required_clicks:
        daily = min(control.clicks, variant.clicks) / days if days else 0
        missing = v.required_clicks - min(control.clicks, variant.clicks)
        remaining = int(-(-missing // daily)) if daily > 0 else None
    cpl_change = (variant.cpl / control.cpl - 1) if control.cpl and variant.cpl else None
    return {
        "window": {"start": exp.start_date, "end": end, "days_with_data": days, "planned_end": planned_end},
        "control": _arm_out(control), "variant": _arm_out(variant),
        "cpl_change": cpl_change,
        "verdict": {"status": v.status, "label": v.label, "z": v.z, "p_value": v.p_value, "lift": v.lift,
                    "required_clicks_per_arm": v.required_clicks, "estimated_days_remaining": remaining},
        "notes": [
            "Teste z de duas proporções na taxa clique → lead (5% de significância, 80% de poder). O resultado "
            "só é declarado ao atingir o volume ou a duração planejada; antes disso, aparece como tendência.",
            "Leads e cliques atribuídos pela plataforma, não pelo CRM.",
            "Anúncios no mesmo conjunto disputam a verba: o resultado indica, mas não prova, causalidade. "
            "Para causalidade, use o teste A/B nativo da Meta.",
        ],
    }


def conclude(db: Session, client: Client, exp: Experiment, outcome: str, learning: str) -> None:
    # Fotografia do resultado no encerramento (datas como texto ISO: a coluna é JSON).
    exp.final_result = json.loads(json.dumps(evaluation(db, client, exp), default=str))
    exp.outcome, exp.learning = outcome, learning.strip()
    exp.status, exp.concluded_at = "concluded", datetime.now(UTC)
