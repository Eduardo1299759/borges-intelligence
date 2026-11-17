"""Agente 11 — Reporting Intelligence: relatórios diário, semanal e mensal.

Cada relatório responde: o que aconteceu (indicadores e maiores variações), por que pode ter acontecido
(diagnósticos abertos, como hipóteses), o que foi feito (decisões e execuções) e o que será testado
(experimentos e próximos passos). Números sempre com o período e a comparação.
"""
from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import data_intelligence
from app.experiments import service as experiments
from app.models import (
    REC_ADJUST,
    REC_AWAITING,
    Alert,
    ApprovalDecision,
    Campaign,
    Client,
    Execution,
    Experiment,
    Learning,
    Recommendation,
)
from app.services.metrics import Totals, compute_kpis, pct_change, query_totals

KINDS = {"daily": "Relatório diário operacional", "weekly": "Relatório semanal",
         "monthly": "Relatório mensal executivo"}
KPIS = [("spend", "Investimento", "neutral"), ("confirmed_revenue", "Receita confirmada", "up"),
        ("leads", "Leads / conversas", "up"), ("confirmed_sales", "Vendas confirmadas", "up"),
        ("real_cac", "CAC real", "down"), ("confirmed_roas", "ROAS confirmado", "up"),
        ("cpl", "Custo por lead", "down"), ("contribution_profit", "Lucro de contribuição", "up")]


def periods(kind: str, last_day: date) -> tuple[date, date, date, date]:
    if kind == "daily":
        return last_day, last_day, last_day - timedelta(days=1), last_day - timedelta(days=1)
    if kind == "weekly":
        return (last_day - timedelta(days=6), last_day, last_day - timedelta(days=13), last_day - timedelta(days=7))
    # mensal: o último mês completo
    month_end = last_day if last_day.day == calendar.monthrange(last_day.year, last_day.month)[1] \
        else last_day.replace(day=1) - timedelta(days=1)
    start = month_end.replace(day=1)
    prev_end = start - timedelta(days=1)
    return start, month_end, prev_end.replace(day=1), prev_end


def _brl(v: float | None) -> str:
    return "indisponível" if v is None else "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:+.0f}%".replace(".", ",")


def build(db: Session, client: Client, kind: str, last_day: date) -> dict[str, Any]:
    start, end, p_start, p_end = periods(kind, last_day)
    margin = float(client.gross_margin_pct) if client.gross_margin_pct is not None else None
    tot = query_totals(db, client.id, start, end)
    prev = query_totals(db, client.id, p_start, p_end)
    cur_k = compute_kpis(tot.get(None, Totals()), margin)
    prev_k = compute_kpis(prev.get(None, Totals()), margin)
    kpis = [{"key": k, "label": label, "good": good, "current": cur_k[k], "previous": prev_k[k],
             "change": pct_change(cur_k[k], prev_k[k])} for k, label, good in KPIS]

    camps = {c.id: c for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    by_c, by_p = query_totals(db, client.id, start, end, "campaign_id"), query_totals(db, client.id, p_start, p_end,
                                                                                         "campaign_id")
    campaigns, highlights = [], []
    for cid, t in sorted(by_c.items(), key=lambda kv: -(kv[1].spend or 0)):
        k, pk = compute_kpis(t, margin), compute_kpis(by_p.get(cid, Totals()), margin)
        name = camps[cid].name if cid in camps else str(cid)
        row = {"name": name, "platform": camps[cid].platform if cid in camps else None, "spend": k["spend"],
               "spend_change": pct_change(k["spend"], pk["spend"]), "leads": k["leads"], "cpl": k["cpl"],
               "cpl_change": pct_change(k["cpl"], pk["cpl"]), "sales": k["confirmed_sales"], "cac": k["real_cac"],
               "cac_change": pct_change(k["real_cac"], pk["real_cac"]), "roas": k["confirmed_roas"]}
        campaigns.append(row)
        if (k["leads"] or 0) >= 10 and row["cpl_change"] is not None and abs(row["cpl_change"]) >= 0.2:
            highlights.append(f"“{name}”: custo por lead {_pct(row['cpl_change'])} ({_brl(pk['cpl'])} → "
                              f"{_brl(k['cpl'])}).")
        if (k["confirmed_sales"] or 0) >= 5 and row["cac_change"] is not None and abs(row["cac_change"]) >= 0.2:
            highlights.append(f"“{name}”: CAC real {_pct(row['cac_change'])} ({_brl(pk['real_cac'])} → "
                              f"{_brl(k['real_cac'])}).")

    d0 = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    d1 = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    pending = db.scalars(select(Recommendation).where(Recommendation.client_id == client.id,
                                                      Recommendation.status.in_([REC_AWAITING, REC_ADJUST]))
                         .order_by(Recommendation.priority_score.desc()).limit(5)).all()
    decisions = db.execute(select(ApprovalDecision, Recommendation)
                           .join(Recommendation, ApprovalDecision.recommendation_id == Recommendation.id)
                           .where(ApprovalDecision.client_id == client.id, ApprovalDecision.created_at >= d0,
                                  ApprovalDecision.created_at < d1)).all()
    executions = db.execute(select(Execution, Recommendation)
                            .join(Recommendation, Execution.recommendation_id == Recommendation.id)
                            .where(Execution.client_id == client.id, Execution.started_at >= d0,
                                   Execution.started_at < d1)).all()
    exps = db.scalars(select(Experiment).where(Experiment.client_id == client.id,
                                               Experiment.status.in_(["running", "concluded"]))).all()
    exps = [e for e in exps if e.status == "running" or (e.concluded_at and d0 <= e.concluded_at < d1)]
    learnings = db.scalars(select(Learning).where(Learning.client_id == client.id, Learning.created_at >= d0,
                                                  Learning.created_at < d1)).all()
    alerts = db.scalars(select(Alert).where(Alert.client_id == client.id, Alert.status == "open")
                        .order_by(Alert.id.desc()).limit(10)).all()
    quality = data_intelligence.validate(db, client, start, end)

    k = {x["key"]: x for x in kpis}
    summary = (f"Investimento de {_brl(k['spend']['current'])} ({_pct(k['spend']['change'])} sobre o período anterior)"
               f", {int(k['leads']['current'] or 0)} leads e "
               + (f"{int(k['confirmed_sales']['current'])} vendas confirmadas, com CAC real de "
                  f"{_brl(k['real_cac']['current'])}" if k["confirmed_sales"]["current"] is not None
                  else "vendas confirmadas indisponíveis (sem CRM/pedidos)")
               + (f" (meta {_brl(float(client.target_cac))})" if client.target_cac is not None and
                  k["real_cac"]["current"] is not None else "") + ".")
    if highlights:
        summary += f" Maiores variações: {highlights[0]}"
    if pending:
        summary += f" Prioridade: {pending[0].title}."

    def exp_out(e: Experiment) -> dict[str, Any]:
        ev = e.final_result if e.status == "concluded" else experiments.evaluation(db, client, e)
        return {"name": e.name, "status": e.status, "hypothesis": e.hypothesis, "outcome": e.outcome,
                "learning": e.learning, "verdict": (ev or {}).get("verdict", {}).get("label")}

    return {
        "kind": kind, "label": KINDS[kind], "client": client.name, "is_demo": client.data_mode == "demo",
        "currency": client.currency, "period": {"start": str(start), "end": str(end)},
        "compare": {"start": str(p_start), "end": str(p_end)}, "sources": quality["sources"],
        "executive_summary": summary, "kpis": kpis, "campaigns": campaigns, "highlights": highlights,
        "why": [{"title": r.title, "problem": r.problem, "probable_cause": r.probable_cause,
                 "hypothesis": r.hypothesis, "priority": r.priority, "confidence": r.confidence} for r in pending],
        "next_steps": [{"title": r.title, "action": r.recommended_action, "validation": r.validation_metric}
                       for r in pending],
        "actions_done": [{"title": r.title, "decision": d.decision, "comment": d.comment, "at": str(d.created_at)}
                         for d, r in decisions],
        "executions": [{"title": r.title, "mode": e.mode, "status": e.status, "before": e.before_state,
                        "after": e.after_state, "verified": e.verified} for e, r in executions],
        "experiments": [exp_out(e) for e in exps],
        "learnings": [{"title": lr.title, "status": lr.status, "reliability": lr.reliability} for lr in learnings],
        "alerts": [{"title": a.title, "severity": a.severity, "detail": a.detail} for a in alerts],
        "data_quality": quality["issues"],
        "notes": ["Variações comparam com o período anterior de mesmo tamanho.",
                  "Diagnósticos são hipóteses a validar; correlação não é causalidade."],
    }
