"""Agente 02 — Performance Auditor: monta o retrato de cada campanha para o motor de decisão."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.decision.engine import AccountContext, CampaignSnapshot
from app.models import Campaign, Client
from app.services.metrics import Totals, compute_kpis, query_totals


def build(db: Session, client: Client, start: date, end: date, sources: str
          ) -> tuple[AccountContext, list[CampaignSnapshot]]:
    margin = float(client.gross_margin_pct) if client.gross_margin_pct is not None else None
    mid = start + timedelta(days=((end - start).days + 1) // 2)
    full = query_totals(db, client.id, start, end, "campaign_id")
    first = query_totals(db, client.id, start, mid - timedelta(days=1), "campaign_id")
    second = query_totals(db, client.id, mid, end, "campaign_id")
    account = Totals()
    for t in full.values():
        account = account + t
    acc = AccountContext(
        target_cac=float(client.target_cac) if client.target_cac is not None else None,
        target_roas=float(client.target_roas) if client.target_roas is not None else None,
        margin_pct=margin,
        max_budget_change_pct=float(client.max_budget_change_pct),
        kpis=compute_kpis(account, margin),
        period_label=f"{start.isoformat()} a {end.isoformat()}",
        sources=sources,
    )
    snapshots = []
    for camp in db.scalars(select(Campaign).where(Campaign.client_id == client.id).order_by(Campaign.id)):
        if camp.id not in full:
            continue
        t = full[camp.id]
        snapshots.append(CampaignSnapshot(
            campaign_id=camp.id, name=camp.name, platform=camp.platform,
            daily_budget=float(camp.daily_budget) if camp.daily_budget is not None else None,
            kpis=compute_kpis(t, margin),
            first_half=compute_kpis(first.get(camp.id, Totals()), margin),
            second_half=compute_kpis(second.get(camp.id, Totals()), margin),
            spend_share=(t.spend / account.spend) if t.spend and account.spend else None,
        ))
    return acc, snapshots
