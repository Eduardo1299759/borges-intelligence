"""Agente 05 — Creative Intelligence: biblioteca de criativos (anúncios da Meta) com classificação.

Classificação relativa à própria campanha (mesmo público e oferta), pelo custo por lead do período:
- sem_resultado: investiu 3x o custo por lead da campanha sem nenhum lead;
- vencedor: 10+ leads e custo por lead até 80% do da campanha;
- fraco: 5+ leads e custo por lead 1,5x o da campanha ou mais;
- pouco_volume: menos de 5 leads (ainda não dá para julgar);
- na_media: o restante.
Tendência: CTR da 2ª metade do período 20% ou mais abaixo da 1ª indica desgaste.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ad, AdSet, BreakdownDaily, Campaign, Client

LABELS = {"sem_resultado": "Sem resultado", "vencedor": "Vencedor", "fraco": "Abaixo da média",
          "pouco_volume": "Pouco volume", "na_media": "Na média"}


def _totals(db: Session, client: Client, start: date, end: date) -> dict[int, list[float]]:
    rows = db.execute(
        select(BreakdownDaily.ad_id, func.sum(BreakdownDaily.spend), func.sum(BreakdownDaily.impressions),
               func.sum(BreakdownDaily.clicks), func.sum(BreakdownDaily.leads))
        .where(BreakdownDaily.client_id == client.id, BreakdownDaily.ad_id.is_not(None),
               BreakdownDaily.date >= start, BreakdownDaily.date <= end)
        .group_by(BreakdownDaily.ad_id)
    ).all()
    return {r[0]: [float(v or 0) for v in r[1:]] for r in rows}


def classify(spend: float, leads: float, camp_cpl: float | None) -> str:
    cpl = spend / leads if leads else None
    if camp_cpl and leads == 0 and spend >= 3 * camp_cpl:
        return "sem_resultado"
    if leads < 5:
        return "pouco_volume"
    if camp_cpl and cpl is not None and leads >= 10 and cpl <= 0.8 * camp_cpl:
        return "vencedor"
    if camp_cpl and cpl is not None and cpl >= 1.5 * camp_cpl:
        return "fraco"
    return "na_media"


def library(db: Session, client: Client, start: date, end: date) -> list[dict[str, Any]]:
    mid = start + timedelta(days=((end - start).days + 1) // 2)
    full = _totals(db, client, start, end)
    first = _totals(db, client, start, mid - timedelta(days=1))
    second = _totals(db, client, mid, end)
    ads = {a.id: a for a in db.scalars(select(Ad).where(Ad.client_id == client.id))}
    sets = {s.id: s for s in db.scalars(select(AdSet).where(AdSet.client_id == client.id))}
    camps = {c.id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    camp_tot: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for ad_id, (spend, _imps, _clicks, leads) in full.items():
        camp_tot[ads[ad_id].campaign_id][0] += spend
        camp_tot[ads[ad_id].campaign_id][1] += leads
    out = []
    for ad_id, (spend, imps, clicks, leads) in full.items():
        ad = ads[ad_id]
        c_spend, c_leads = camp_tot[ad.campaign_id]
        camp_cpl = c_spend / c_leads if c_leads else None
        ctr1 = first[ad_id][2] / first[ad_id][1] if ad_id in first and first[ad_id][1] else None
        ctr2 = second[ad_id][2] / second[ad_id][1] if ad_id in second and second[ad_id][1] else None
        trend = None
        if ctr1 and ctr2 is not None:
            trend = "ctr_caindo" if ctr2 / ctr1 <= 0.8 else "ctr_subindo" if ctr2 / ctr1 >= 1.2 else "estavel"
        cls = classify(spend, leads, camp_cpl)
        out.append({
            "ad_id": ad_id, "name": ad.name, "status": ad.status, "ad_set": sets[ad.ad_set_id].name,
            "campaign_id": ad.campaign_id, "campaign": camps[ad.campaign_id].name,
            "is_demo": camps[ad.campaign_id].is_demo,
            "spend": spend, "impressions": imps, "clicks": clicks, "leads": leads,
            "ctr": clicks / imps if imps else None, "cpl": spend / leads if leads else None,
            "campaign_cpl": camp_cpl, "spend_share_in_campaign": spend / c_spend if c_spend else None,
            "class": cls, "class_label": LABELS[cls], "trend": trend, "ctr_first_half": ctr1, "ctr_second_half": ctr2,
        })
    order = {"vencedor": 0, "na_media": 1, "pouco_volume": 2, "fraco": 3, "sem_resultado": 4}
    out.sort(key=lambda a: (a["campaign"], order[a["class"]], -a["spend"]))
    return out
