"""Agente 00 — Borges Core.

Fase 1: orquestração determinística. COLETAR(já armazenado) → VALIDAR → ANALISAR → DIAGNOSTICAR →
RECOMENDAR → (aguarda APROVAR). Não há LLM: a pergunta do usuário é registrada e usada apenas para
destacar as recomendações do tema perguntado. Interpretação em linguagem natural entra na Fase 3.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import data_intelligence, financial, performance_auditor, specialists
from app.decision import engine
from app.decision.specialists import evaluate_entities
from app.models import REC_ADJUST, REC_AWAITING, REC_INFO, AnalysisRun, Client, Recommendation, User
from app.services import audit

TOPICS = {
    "cac_above_target": ("cac", "custo por cliente", "caro", "reduzir"),
    "lead_quality": ("lead", "qualidade", "conversa", "whatsapp", "cac"),
    "creative_fatigue": ("criativo", "fadiga", "ctr", "anúncio", "anuncio"),
    "tracking_divergence": ("rastreamento", "tracking", "atribuição", "atribuicao", "pixel", "conversão"),
    "scale_winner": ("escalar", "escala", "aumentar", "orçamento", "orcamento", "roas"),
    "ad_no_results": ("anúncio", "anuncio", "pausar", "desperdício", "desperdicio", "sem resultado"),
    "ad_cpl_outlier": ("anúncio", "anuncio", "criativo", "custo por lead", "cpl"),
    "ad_dilution": ("estrutura", "consolidar", "anúncios", "anuncios"),
    "conversion_value_missing": ("conversão", "conversao", "valor", "rastreamento", "google"),
}

# Com estes diagnósticos de campanha, os especialistas não opinam sobre anúncios: os dados são poucos
# demais ou não confiáveis, e uma recomendação de anúncio esconderia o problema principal.
SUPPRESS_SPECIALISTS = {"insufficient_sample", "tracking_divergence"}


def analyze(db: Session, client: Client, user: User | None, question: str, start: date, end: date) -> AnalysisRun:
    run = AnalysisRun(client_id=client.id, requested_by=user.id if user else None, question=question,
                      period_start=start, period_end=end, status="running", is_demo=client.data_mode == "demo")
    db.add(run)
    db.flush()
    quality = data_intelligence.validate(db, client, start, end)
    period = f"{start.isoformat()} a {end.isoformat()}"

    if not quality["has_data"]:
        run.status = "completed"
        run.summary = {
            "answer": "Não há dados para este cliente no período. Nenhuma análise ou recomendação foi produzida. "
                      "Conecte uma fonte de dados (Fase 2) ou use um cliente em modo demonstração.",
            "data_quality": quality, "finance": None, "recommendation_ids": [], "matched_ids": [], "period": period,
        }
        audit.record(db, action="analysis.completed", actor=user, client_id=client.id, entity_type="analysis_run",
                     entity_id=run.id, details={"has_data": False, "period": period})
        return run

    sources = " + ".join(quality["sources"])
    acc, snapshots = performance_auditor.build(db, client, start, end, sources)
    campaign_drafts = [engine.evaluate(s, acc) for s in snapshots]
    entities = specialists.entity_stats(db, client, start, end)
    specialist_drafts = []
    for snap, draft in zip(snapshots, campaign_drafts, strict=True):
        if draft.rule not in SUPPRESS_SPECIALISTS:
            specialist_drafts += evaluate_entities(snap, entities.get(snap.campaign_id, []), acc)
    drafts = engine.prioritize(campaign_drafts + specialist_drafts, {s.campaign_id: s for s in snapshots})

    open_recs = {
        (r.campaign_id, r.rule, r.ad_set_id, r.ad_id): r
        for r in db.scalars(select(Recommendation).where(
            Recommendation.client_id == client.id, Recommendation.status.in_([REC_AWAITING, REC_ADJUST])))
    }
    ids: list[int] = []
    reused = 0
    for d in drafts:
        existing = open_recs.get((d.campaign_id, d.rule, d.ad_set_id, d.ad_id))
        if existing is not None:  # já há uma pendência idêntica: não duplicar na fila de aprovação
            ids.append(existing.id)
            reused += 1
            continue
        rec = Recommendation(
            client_id=client.id, analysis_run_id=run.id, campaign_id=d.campaign_id, ad_set_id=d.ad_set_id,
            ad_id=d.ad_id, agent=d.agent, rule=d.rule,
            title=d.title, problem=d.problem, evidence=d.evidence, probable_cause=d.probable_cause,
            alternatives=d.alternatives, hypothesis=d.hypothesis, action_type=d.action_type,
            action_payload=d.action_payload, recommended_action=d.recommended_action,
            expected_impact=d.expected_impact, priority=d.priority, priority_score=d.priority_score,
            confidence=d.confidence, risks=d.risks, requires_approval=d.requires_approval,
            validation_metric=d.validation_metric, is_demo=run.is_demo,
            status=REC_AWAITING if d.requires_approval else REC_INFO,
        )
        db.add(rec)
        db.flush()
        ids.append(rec.id)

    q = question.lower()
    asked_rules = {rule for rule, words in TOPICS.items() if any(w in q for w in words)}
    matched = [i for i, d in zip(ids, drafts, strict=True) if d.rule in asked_rules]
    actionable = sum(1 for d in drafts if d.requires_approval)
    answer = (
        f"Analisei {len(campaign_drafts)} campanha(s) de {period}"
        + (" com DADOS DEMONSTRATIVOS" if run.is_demo else "")
        + (f", e os especialistas Meta e Google encontraram {len(specialist_drafts)} ponto(s) em anúncios e "
           "grupos de anúncios" if specialist_drafts else "")
        + f". {actionable} recomendação(ões) exigem sua aprovação e {len(drafts) - actionable} campanha(s) devem "
        "ser mantidas sem alteração."
    )
    if reused:
        answer += f" {reused} delas já estavam pendentes na Central de aprovação e não foram duplicadas."
    if asked_rules and not matched:
        answer += " Não encontrei evidências, nos dados atuais, do problema específico mencionado na pergunta."

    run.status = "completed"
    run.summary = {
        "answer": answer, "period": period, "data_quality": quality,
        "finance": financial.assess(acc.kpis, client),
        "recommendation_ids": ids, "matched_ids": matched,
        "agents": ["Borges Core", "Data Intelligence", "Performance Auditor", "Meta Ads Specialist",
                   "Google Ads Specialist", "Financial Intelligence"],
        "method": "Regras determinísticas (sem LLM).",
    }
    audit.record(db, action="analysis.completed", actor=user, client_id=client.id, entity_type="analysis_run",
                 entity_id=run.id,
                 details={"period": period, "campaigns": len(campaign_drafts),
                          "specialist_findings": len(specialist_drafts), "recommendation_ids": ids, "reused": reused})
    return run
