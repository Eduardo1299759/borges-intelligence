"""Grava no banco o que um conector de leitura entrega (upsert idempotente por chave natural)."""
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ReadConnector
from app.models import AdAccount, Campaign, Client, MetricDaily, SalesDaily


def ingest(db: Session, client: Client, connector: ReadConnector, start: date, end: date) -> dict[str, int]:
    now = datetime.now(UTC)
    accounts: dict[tuple[str, str], AdAccount] = {
        (a.platform, a.external_id): a
        for a in db.scalars(select(AdAccount).where(AdAccount.client_id == client.id))
    }
    campaigns: dict[str, Campaign] = {
        c.external_id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))
    }
    for rec in connector.campaigns():
        acc = accounts.get((rec.platform, rec.account_external_id))
        if acc is None:
            acc = AdAccount(client_id=client.id, platform=rec.platform, external_id=rec.account_external_id,
                            name=rec.account_name, is_demo=connector.is_demo)
            db.add(acc)
            db.flush()
            accounts[(rec.platform, rec.account_external_id)] = acc
        acc.last_synced_at = now
        camp = campaigns.get(rec.external_id)
        if camp is None:
            camp = Campaign(client_id=client.id, ad_account_id=acc.id, external_id=rec.external_id,
                            platform=rec.platform, is_demo=connector.is_demo, name=rec.name,
                            daily_budget=rec.daily_budget)
            db.add(camp)
            campaigns[rec.external_id] = camp
        camp.name, camp.objective, camp.status = rec.name, rec.objective, rec.status
    db.flush()

    existing_m = {
        (m.campaign_id, m.date): m
        for m in db.scalars(select(MetricDaily).where(
            MetricDaily.client_id == client.id, MetricDaily.source == connector.source,
            MetricDaily.date >= start, MetricDaily.date <= end))
    }
    n_metrics = 0
    for rec in connector.metrics(start, end):
        camp = campaigns[rec.campaign_external_id]
        row = existing_m.get((camp.id, rec.date))
        if row is None:
            row = MetricDaily(client_id=client.id, campaign_id=camp.id, date=rec.date, source=connector.source,
                              is_demo=connector.is_demo)
            db.add(row)
        for field in ("spend", "impressions", "reach", "clicks", "link_clicks", "leads",
                      "attributed_purchases", "attributed_revenue"):
            setattr(row, field, getattr(rec, field))
        row.synced_at = now
        n_metrics += 1

    sales_source = getattr(connector, "sales_source", connector.source)
    existing_s = {
        (s.campaign_id, s.date): s
        for s in db.scalars(select(SalesDaily).where(
            SalesDaily.client_id == client.id, SalesDaily.source == sales_source,
            SalesDaily.date >= start, SalesDaily.date <= end))
    }
    n_sales = 0
    for rec in connector.sales(start, end):
        camp = campaigns[rec.campaign_external_id]
        row = existing_s.get((camp.id, rec.date))
        if row is None:
            row = SalesDaily(client_id=client.id, campaign_id=camp.id, date=rec.date, source=sales_source,
                             is_demo=connector.is_demo, confirmed_sales=0, confirmed_revenue=0)
            db.add(row)
        row.confirmed_sales, row.confirmed_revenue = rec.confirmed_sales, rec.confirmed_revenue
        n_sales += 1
    db.flush()
    return {"campaigns": len(campaigns), "metric_rows": n_metrics, "sales_rows": n_sales}
