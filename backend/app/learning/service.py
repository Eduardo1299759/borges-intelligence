"""Memória de aprendizados.

Regra central: um aprendizado só vira "validado" com evidência de experimento (teste estatístico com resultado
significativo). Comparações antes/depois e anotações manuais entram como hipótese. Assim, uma suposição nunca
vira regra permanente sem validação.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Experiment, Learning

SIGNIFICANT = {"significant_better", "significant_worse"}


def from_experiment(db: Session, client: Client, exp: Experiment, actor: str) -> Learning:
    result = exp.final_result or {}
    verdict = result.get("verdict", {})
    significant = verdict.get("status") in SIGNIFICANT and exp.outcome in ("success", "failure")
    p = verdict.get("p_value")
    reliability = "alta" if significant and p is not None and p < 0.01 else "média" if significant else "baixa"
    lift = verdict.get("lift")
    numbers = f" Variação na taxa clique → lead: {lift * 100:+.1f}%".replace(".", ",") if lift is not None else ""
    learning = Learning(
        client_id=client.id, title=exp.name,
        statement=f"{exp.learning} (Hipótese testada: {exp.hypothesis}.{numbers}; resultado: "
                  f"{verdict.get('label', 'sem avaliação')}.)",
        context=f"Variável: {exp.variable}. Experimento #{exp.id}.",
        source_type="experiment", source_ref=f"experiment:{exp.id}",
        evidence={"experiment_id": exp.id, "verdict": verdict, "outcome": exp.outcome},
        status="validated" if significant else "hypothesis", reliability=reliability, created_by=actor,
        validated_at=datetime.now(UTC) if significant else None,
    )
    db.add(learning)
    db.flush()
    return learning


def from_impact(db: Session, client: Client, impact: dict[str, Any]) -> Learning | None:
    ref = f"execution:{impact['execution_id']}"
    if db.scalar(select(Learning.id).where(Learning.client_id == client.id, Learning.source_ref == ref)):
        return None
    label = {"real_cac": "CAC real", "cpl": "custo por lead"}[impact["metric"]]
    change = impact["metric_change"]
    text = "sem dado suficiente" if change is None else f"{change * 100:+.0f}%".replace(".", ",")
    learning = Learning(
        client_id=client.id, title=f"Efeito de {impact['action']} em “{impact['campaign']}”",
        statement=f"Nos 7 dias após a mudança, o {label} variou {text} em relação aos 7 dias anteriores. "
                  "Comparação antes/depois: não prova causa (sazonalidade e outras mudanças interferem).",
        context=f"Campanha: {impact['campaign']}.", source_type="execution_impact", source_ref=ref,
        evidence=impact, status="hypothesis", reliability="baixa", created_by="Rotina diária",
    )
    db.add(learning)
    db.flush()
    return learning


def search(db: Session, client: Client, query: str | None, status: str | None = None) -> list[Learning]:
    rows = db.scalars(select(Learning).where(Learning.client_id == client.id).order_by(Learning.id.desc())).all()
    if status:
        rows = [r for r in rows if r.status == status]
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 2]
    if not terms:
        return sorted(rows, key=lambda r: (r.status != "validated", -r.id))
    scored = []
    for r in rows:
        text = f"{r.title} {r.statement} {r.context or ''}".lower()
        score = sum(text.count(t) for t in terms)
        if score:
            scored.append((score, r))
    return [r for _, r in sorted(scored, key=lambda x: (x[1].status != "validated", -x[0], -x[1].id))]


def validate_with_experiment(db: Session, learning: Learning, exp: Experiment) -> None:
    verdict = (exp.final_result or {}).get("verdict", {})
    if exp.status != "concluded" or verdict.get("status") not in SIGNIFICANT:
        raise ValueError("Só um experimento concluído com resultado significativo valida um aprendizado.")
    learning.status = "validated"
    learning.reliability = "alta" if (verdict.get("p_value") or 1) < 0.01 else "média"
    learning.evidence = {**(learning.evidence or {}), "experiment_id": exp.id, "verdict": verdict}
    learning.validated_at = datetime.now(UTC)
