"""Agente 07 — Sales Intelligence: funil comercial, tempo de resposta e motivos de perda, por campanha.

Funil por etapa alcançada: um lead em "proposta" passou por novo, contato e qualificado. Leads perdidos contam
só como entrada (o CRM exportado não diz em que etapa se perderam).
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Client, LeadRecord
from app.services.metrics import query_totals

ORDER = ["novo", "contato", "qualificado", "proposta", "venda"]
LABELS = {"novo": "Entrada", "contato": "Contato feito", "qualificado": "Qualificado", "proposta": "Proposta",
          "venda": "Venda"}
SLOW_MINUTES = 30
MIN_LEADS_FOR_RULES = 20


def _reached(stage: str) -> int:
    return ORDER.index(stage) if stage in ORDER else 0


def _percentile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def funnel(leads: list[LeadRecord]) -> list[dict[str, Any]]:
    out = []
    for i, stage in enumerate(ORDER):
        reached = sum(1 for lead in leads if lead.stage != "perdido" and _reached(lead.stage) >= i) + (
            sum(1 for lead in leads if lead.stage == "perdido") if i == 0 else 0)
        out.append({"stage": stage, "label": LABELS[stage], "count": reached})
    for i in range(1, len(out)):
        prev = out[i - 1]["count"]
        out[i]["rate_from_previous"] = out[i]["count"] / prev if prev else None
    return out


def summary(db: Session, client: Client, start: date, end: date) -> dict[str, Any]:
    leads = db.scalars(select(LeadRecord).where(LeadRecord.client_id == client.id, LeadRecord.date >= start,
                                                LeadRecord.date <= end)).all()
    camps = {c.id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    ads = query_totals(db, client.id, start, end, "campaign_id")
    by_camp: dict[int | None, list[LeadRecord]] = defaultdict(list)
    for lead in leads:
        by_camp[lead.campaign_id].append(lead)
    rows = []
    for cid in sorted(set(by_camp) | {c for c in ads if ads[c].leads}, key=lambda c: (c is None, c or 0)):
        group = by_camp.get(cid, [])
        t = ads.get(cid) if cid is not None else None
        sales = sum(1 for lead in group if lead.stage == "venda")
        qualified = sum(1 for lead in group if lead.stage != "perdido" and _reached(lead.stage) >= 2)
        times = [lead.response_minutes for lead in group if lead.response_minutes is not None]
        spend = t.spend if t else None
        rows.append({
            "campaign_id": cid, "campaign": camps[cid].name if cid in camps else "Sem campanha identificada",
            "platform_leads": t.leads if t else None, "crm_leads": len(group), "qualified": qualified,
            "sales": sales, "lost": sum(1 for lead in group if lead.stage == "perdido"),
            "qualified_rate": qualified / len(group) if group else None,
            "sale_rate": sales / len(group) if group else None,
            "spend": spend, "cost_per_crm_lead": spend / len(group) if spend and group else None,
            "cost_per_sale": spend / sales if spend and sales else None,
            "median_response_min": statistics.median(times) if times else None,
        })
    times = [lead.response_minutes for lead in leads if lead.response_minutes is not None]
    return {
        "period": {"start": start, "end": end},
        "has_crm_data": bool(leads),
        "total_leads": len(leads),
        "funnel": funnel(leads),
        "by_campaign": rows,
        "response": {"answered": len(times), "median_min": statistics.median(times) if times else None,
                     "p75_min": _percentile(times, 0.75),
                     "within_5_min": sum(1 for t in times if t <= 5) / len(times) if times else None},
        "lost_reasons": Counter(lead.lost_reason or "não informado" for lead in leads
                                if lead.stage == "perdido").most_common(8),
        "notes": ["Funil por etapa alcançada; leads perdidos contam só na entrada.",
                  "Leads da plataforma (atribuição dela) e leads do CRM são contados de formas diferentes; "
                  "diferenças grandes indicam problema de rastreamento ou de registro no CRM."],
    }
