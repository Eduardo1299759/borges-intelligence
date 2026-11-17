"""Agentes 03 e 04 — Meta Ads Specialist e Google Ads Specialist: busca os totais por anúncio/grupo."""
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.decision.specialists import EntityStats
from app.models import Ad, AdSet, BreakdownDaily, Client


def entity_stats(db: Session, client: Client, start: date, end: date) -> dict[int, list[EntityStats]]:
    """Totais do período por campanha, no nível mais baixo disponível (anúncio ou grupo)."""
    rows = db.execute(
        select(BreakdownDaily.campaign_id, BreakdownDaily.ad_set_id, BreakdownDaily.ad_id,
               func.sum(BreakdownDaily.spend), func.sum(BreakdownDaily.impressions),
               func.sum(BreakdownDaily.clicks), func.sum(BreakdownDaily.leads))
        .where(BreakdownDaily.client_id == client.id, BreakdownDaily.date >= start, BreakdownDaily.date <= end)
        .group_by(BreakdownDaily.campaign_id, BreakdownDaily.ad_set_id, BreakdownDaily.ad_id)
    ).all()
    sets = {s.id: s for s in db.scalars(select(AdSet).where(AdSet.client_id == client.id))}
    ads = {a.id: a for a in db.scalars(select(Ad).where(Ad.client_id == client.id))}
    out: dict[int, list[EntityStats]] = defaultdict(list)
    for campaign_id, set_id, ad_id, spend, imps, clicks, leads in rows:
        ad = ads.get(ad_id) if ad_id else None
        out[campaign_id].append(EntityStats(
            ad_set_id=set_id, ad_set_name=sets[set_id].name, ad_id=ad_id, ad_name=ad.name if ad else None,
            status=(ad.status if ad else sets[set_id].status),
            spend=None if spend is None else float(spend), impressions=None if imps is None else float(imps),
            clicks=None if clicks is None else float(clicks), leads=None if leads is None else float(leads),
        ))
    for items in out.values():
        items.sort(key=lambda e: e.spend or 0, reverse=True)
    return out
