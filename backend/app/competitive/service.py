"""Agente 06 — Competitive Intelligence: resumo de anúncios públicos de concorrentes.

Fontes: captura manual (link e texto do anúncio) e, quando houver token aprovado pela Meta, a Biblioteca de
Anúncios (não ativada nesta versão). Nunca afirma que um anúncio de concorrente dá lucro: não há dado
financeiro dele. Tempo no ar sugere investimento continuado, não prova resultado.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import runner
from app.models import Client, Competitor, CompetitorAd

SYSTEM = """Você é o Competitive Intelligence de uma agência de tráfego pago. Analise anúncios públicos de \
concorrentes (JSON) e responda em português do Brasil.

Regras:
- Use apenas o texto dos anúncios fornecidos. Não invente anúncios, ofertas, preços ou resultados.
- Nunca afirme que um anúncio de concorrente é lucrativo ou "funciona": não há dados financeiros dele. Tempo \
no ar indica investimento continuado, não resultado.
- Ao citar um número (preço, desconto), copie-o exatamente como está no anúncio.
- Oportunidades devem ser ideias de teste para o cliente, com o motivo, não conclusões."""

SCHEMA = {
    "type": "object",
    "properties": {
        "angles": {"type": "array", "items": {"type": "object", "properties": {
            "angle": {"type": "string"}, "competitors": {"type": "array", "items": {"type": "string"}},
            "example": {"type": "string"}}, "required": ["angle", "competitors", "example"],
            "additionalProperties": False}},
        "offers": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "object", "properties": {
            "idea": {"type": "string"}, "rationale": {"type": "string"}}, "required": ["idea", "rationale"],
            "additionalProperties": False}},
    },
    "required": ["angles", "offers", "opportunities"],
    "additionalProperties": False,
}


def overview(db: Session, client: Client) -> dict[str, Any]:
    competitors = db.scalars(select(Competitor).where(Competitor.client_id == client.id)
                             .order_by(Competitor.name)).all()
    ads = db.scalars(select(CompetitorAd).where(CompetitorAd.client_id == client.id)
                     .order_by(CompetitorAd.captured_at.desc())).all()
    by_comp = Counter(a.competitor_id for a in ads)
    today = date.today()
    return {
        "competitors": [{"id": c.id, "name": c.name, "website": c.website, "facebook_page": c.facebook_page,
                         "notes": c.notes, "ads": by_comp.get(c.id, 0)} for c in competitors],
        "ads": [{"id": a.id, "competitor_id": a.competitor_id, "source": a.source, "url": a.url, "ad_text": a.ad_text,
                 "offer": a.offer, "format": a.format, "first_seen": a.first_seen, "captured_at": a.captured_at,
                 "days_running": (today - a.first_seen).days if a.first_seen else None} for a in ads],
        "formats": dict(Counter(a.format or "não informado" for a in ads)),
    }


def insights(db: Session, client: Client) -> dict[str, Any]:
    data = overview(db, client)
    names = {c["id"]: c["name"] for c in data["competitors"]}
    ads = [{"concorrente": names[a["competitor_id"]], "texto": a["ad_text"], "oferta": a["offer"],
            "formato": a["format"], "dias_no_ar": a["days_running"]} for a in data["ads"]]
    if not ads:
        return {"source": "nenhuma", "note": "Cadastre anúncios de concorrentes para gerar a análise."}
    facts_text = json.dumps({"cliente": client.name, "segmento": client.segment, "anuncios": ads},
                            ensure_ascii=False, default=str)
    result = runner.run_structured(db, purpose="competitive_insights", client_id=client.id, system=SYSTEM,
                                   user_text=f"Fatos (JSON):\n{facts_text}", schema=SCHEMA,
                                   guard_numbers_against=facts_text)
    if result is not None and result.ok:
        return {"source": "ia", "model": result.model, "cost_usd": result.cost_usd, **result.data}
    long_running = sorted((a for a in data["ads"] if a["days_running"] is not None),
                          key=lambda a: a["days_running"], reverse=True)[:3]
    return {
        "source": "regras",
        "note": result.error if result is not None else "Ative a IA em Configurações para a análise de ângulos.",
        "offers": [f"{names[a['competitor_id']]}: {a['offer']}" for a in data["ads"] if a["offer"]],
        "long_running": [{"competitor": names[a["competitor_id"]], "days_running": a["days_running"],
                          "ad_text": a["ad_text"][:160]} for a in long_running],
        "formats": data["formats"],
    }
