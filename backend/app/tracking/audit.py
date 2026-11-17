"""Tracking & CRO: auditoria que cruza as fontes e aponta onde a mensuração está falhando."""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import data_intelligence
from app.models import Campaign, Client, ImportRun, PageCheck
from app.sales import intelligence
from app.sales.importer import utm_slug
from app.services.metrics import query_totals


def findings(db: Session, client: Client, start: date, end: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(severity: str, area: str, title: str, detail: str) -> None:
        out.append({"severity": severity, "area": area, "title": title, "detail": detail})

    for issue in data_intelligence.validate(db, client, start, end)["issues"]:
        add("media", "Dados", "Qualidade dos dados", issue)
    camps = {c.id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    for cid, t in query_totals(db, client.id, start, end, "campaign_id").items():
        name = camps[cid].name if cid in camps else str(cid)
        if t.attributed_revenue and t.confirmed_revenue and t.confirmed_sales and t.confirmed_sales >= 10:
            ratio = t.attributed_revenue / t.confirmed_revenue
            if ratio >= 1.5 or ratio <= 1 / 1.5:
                add("alta", "Atribuição", f"“{name}”: receita atribuída {ratio:.1f}x a confirmada".replace(".", ","),
                    "Eventos de compra duplicados, janela de atribuição ampla ou vendas que não chegam ao CRM.")
        if cid in camps and camps[cid].platform == "google" and (t.leads or 0) >= 10 and t.attributed_revenue == 0:
            add("media", "Conversões", f"“{name}”: conversões sem valor",
                "Defina valor nas conversões do Google Ads para permitir otimização por valor e ROAS.")
    sales = intelligence.summary(db, client, start, end)
    for row in sales["by_campaign"]:
        if row["campaign_id"] and (row["platform_leads"] or 0) >= 30 and row["crm_leads"] < row["platform_leads"] / 2:
            add("alta", "CRM", f"“{row['campaign']}”: leads não chegam ao CRM",
                f"Plataforma: {row['platform_leads']:.0f} leads; CRM: {row['crm_leads']}.")
    last_orders = db.scalar(select(ImportRun).where(ImportRun.client_id == client.id, ImportRun.kind == "orders")
                            .order_by(ImportRun.id.desc()).limit(1))
    if last_orders and last_orders.stats.get("unmatched_campaigns"):
        values = ", ".join(f"{v} ({n})" for v, n in last_orders.stats["unmatched_campaigns"][:5])
        add("alta", "UTM", "Vendas sem campanha identificada na última importação",
            f"Valores de campanha sem correspondência: {values}. Padronize as UTMs (veja as sugestões abaixo).")
    checks = db.scalars(select(PageCheck).where(PageCheck.client_id == client.id).order_by(PageCheck.id.desc())
                        .limit(5)).all()
    for pc in checks:
        bad = [i["label"] for i in pc.result.get("items", []) if i["ok"] is False]
        if bad:
            add("media", "Página", f"{pc.url}: {len(bad)} problema(s)", ", ".join(bad))
    order = {"alta": 0, "media": 1, "baixa": 2}
    return sorted(out, key=lambda f: order[f["severity"]])


def utm_suggestions(db: Session, client: Client) -> dict[str, Any]:
    camps = db.scalars(select(Campaign).where(Campaign.client_id == client.id).order_by(Campaign.name)).all()
    return {
        "meta_url_parameters": "utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}"
                               "&utm_content={{ad.name}}",
        "google_tracking_template": "{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={campaignid}"
                                    "&utm_content={adgroupid}",
        "campaigns": [{"campaign_id": c.id, "name": c.name, "platform": c.platform, "external_id": c.external_id,
                       "utm_campaign": utm_slug(c.name),
                       "example": f"?utm_source={'facebook' if c.platform == 'meta' else 'google'}"
                                  f"&utm_medium={'paid_social' if c.platform == 'meta' else 'cpc'}"
                                  f"&utm_campaign={quote(utm_slug(c.name))}"} for c in camps],
        "notes": ["Na Meta, cole os parâmetros em 'Parâmetros de URL' do anúncio; os valores {{...}} são preenchidos "
                  "pela própria Meta.",
                  "No Google Ads, use o modelo de acompanhamento no nível da conta; {campaignid} é preenchido pelo "
                  "Google.",
                  "O Borges reconhece a campanha na importação de vendas pelo nome (inclusive no formato da coluna "
                  "utm_campaign acima) ou pelo ID da campanha."],
    }
