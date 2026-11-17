"""Grava no banco o que um conector entrega (upsert idempotente por chave natural) e reconcilia níveis."""
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import Payload, ReadConnector
from app.models import Ad, AdAccount, AdSet, BreakdownDaily, Campaign, Client, MetricDaily, SalesDaily

METRIC_FIELDS = ("spend", "impressions", "reach", "clicks", "link_clicks", "leads", "attributed_purchases",
                 "attributed_revenue")
BREAKDOWN_FIELDS = tuple(f for f in METRIC_FIELDS if f != "reach")


def ingest(db: Session, client: Client, connector: ReadConnector, payload: Payload, start: date, end: date
           ) -> dict[str, int]:
    now = datetime.now(UTC)
    demo = connector.is_demo
    accounts = {(a.platform, a.external_id): a
                for a in db.scalars(select(AdAccount).where(AdAccount.client_id == client.id))}
    campaigns = {c.external_id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    for rec in payload.campaigns:
        acc = accounts.get((rec.platform, rec.account_external_id))
        if acc is None:
            acc = AdAccount(client_id=client.id, platform=rec.platform, external_id=rec.account_external_id,
                            name=rec.account_name, is_demo=demo)
            db.add(acc)
            db.flush()
            accounts[(rec.platform, rec.account_external_id)] = acc
        acc.name, acc.currency, acc.last_synced_at = rec.account_name, rec.currency, now
        camp = campaigns.get(rec.external_id)
        if camp is None:
            camp = Campaign(client_id=client.id, ad_account_id=acc.id, external_id=rec.external_id,
                            platform=rec.platform, is_demo=demo, name=rec.name, daily_budget=rec.daily_budget)
            db.add(camp)
            campaigns[rec.external_id] = camp
        elif not demo:
            # Fonte real: o orçamento da plataforma é a verdade. Em demo, o orçamento vive no Borges
            # (execuções simuladas o alteram) e não deve ser sobrescrito pelo gerador.
            camp.daily_budget = rec.daily_budget
        camp.name, camp.objective, camp.status = rec.name, rec.objective, rec.status
    db.flush()

    ad_sets = {(s.campaign_id, s.external_id): s for s in db.scalars(select(AdSet).where(AdSet.client_id == client.id))}
    by_ext: dict[str, AdSet] = {}
    for rec in payload.ad_sets:
        camp = campaigns[rec.campaign_external_id]
        row = ad_sets.get((camp.id, rec.external_id))
        if row is None:
            row = AdSet(client_id=client.id, campaign_id=camp.id, external_id=rec.external_id, name=rec.name)
            db.add(row)
            ad_sets[(camp.id, rec.external_id)] = row
        row.name, row.status = rec.name, rec.status
        by_ext[rec.external_id] = row
    db.flush()
    ads = {(a.ad_set_id, a.external_id): a for a in db.scalars(select(Ad).where(Ad.client_id == client.id))}
    ad_by_ext: dict[str, Ad] = {}
    for rec in payload.ads:
        parent = by_ext[rec.adset_external_id]
        row = ads.get((parent.id, rec.external_id))
        if row is None:
            row = Ad(client_id=client.id, campaign_id=parent.campaign_id, ad_set_id=parent.id,
                     external_id=rec.external_id, name=rec.name)
            db.add(row)
            ads[(parent.id, rec.external_id)] = row
        row.name, row.status = rec.name, rec.status
        ad_by_ext[rec.external_id] = row
    db.flush()

    def window(model, source):
        return select(model).where(model.client_id == client.id, model.source == source, model.date >= start,
                                   model.date <= end)

    existing_m = {(m.campaign_id, m.date): m for m in db.scalars(window(MetricDaily, connector.source))}
    for rec in payload.metrics:
        camp = campaigns[rec.campaign_external_id]
        row = existing_m.get((camp.id, rec.date))
        if row is None:
            row = MetricDaily(client_id=client.id, campaign_id=camp.id, date=rec.date, source=connector.source,
                              is_demo=demo)
            db.add(row)
            existing_m[(camp.id, rec.date)] = row
        for f in METRIC_FIELDS:
            setattr(row, f, getattr(rec, f))
        row.synced_at = now

    existing_b = {(b.entity_key, b.date): b for b in db.scalars(window(BreakdownDaily, connector.source))}
    for rec in payload.breakdown:
        parent = by_ext[rec.adset_external_id]
        ad = ad_by_ext.get(rec.ad_external_id) if rec.ad_external_id else None
        key = f"ad:{ad.id}" if ad else f"adset:{parent.id}"
        row = existing_b.get((key, rec.date))
        if row is None:
            row = BreakdownDaily(client_id=client.id, campaign_id=parent.campaign_id, ad_set_id=parent.id,
                                 ad_id=ad.id if ad else None, entity_key=key, date=rec.date,
                                 source=connector.source, is_demo=demo)
            db.add(row)
            existing_b[(key, rec.date)] = row
        for f in BREAKDOWN_FIELDS:
            setattr(row, f, getattr(rec, f))

    if connector.sales_source:
        existing_s = {(s.campaign_id, s.date): s for s in db.scalars(window(SalesDaily, connector.sales_source))}
        for rec in payload.sales:
            camp = campaigns[rec.campaign_external_id]
            row = existing_s.get((camp.id, rec.date))
            if row is None:
                row = SalesDaily(client_id=client.id, campaign_id=camp.id, date=rec.date, is_demo=demo,
                                 source=connector.sales_source, confirmed_sales=0, confirmed_revenue=0)
                db.add(row)
                existing_s[(camp.id, rec.date)] = row
            row.confirmed_sales, row.confirmed_revenue = rec.confirmed_sales, rec.confirmed_revenue
    db.flush()
    return {"campaigns": len(payload.campaigns), "ad_sets": len(payload.ad_sets), "ads": len(payload.ads),
            "metric_rows": len(payload.metrics), "breakdown_rows": len(payload.breakdown),
            "sales_rows": len(payload.sales) if connector.sales_source else 0}


def reconcile_levels(payload: Payload) -> list[str]:
    """Compara o investimento da campanha com a soma do nível detalhado, dia a dia.

    Só avalia campanhas que têm detalhamento (Performance Max, por exemplo, não tem grupos).
    Tolerância: 1% ou 0,05 na moeda, o que for maior (arredondamentos da própria plataforma).
    """
    detail: dict[tuple[str, date], Decimal] = defaultdict(Decimal)
    for b in payload.breakdown:
        if b.spend is not None:
            detail[(b.campaign_external_id, b.date)] += b.spend
    names = {c.external_id: c.name for c in payload.campaigns}
    with_detail = {cid for cid, _ in detail}
    off: dict[str, int] = defaultdict(int)
    missing: dict[str, int] = defaultdict(int)
    for m in payload.metrics:
        if m.campaign_external_id not in with_detail or not m.spend:
            continue
        total = detail.get((m.campaign_external_id, m.date))
        if total is None:
            missing[m.campaign_external_id] += 1
        elif abs(total - m.spend) > max(Decimal("0.05"), m.spend * Decimal("0.01")):
            off[m.campaign_external_id] += 1
    issues = [f"“{names.get(c, c)}”: em {n} dia(s) a soma dos anúncios/grupos diverge do total da campanha "
              "em mais de 1%." for c, n in sorted(off.items())]
    issues += [f"“{names.get(c, c)}”: {n} dia(s) com investimento na campanha e sem detalhamento por anúncio/grupo."
               for c, n in sorted(missing.items())]
    return issues
