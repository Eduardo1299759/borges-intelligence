"""Agente 12 — Operations & Safety: decisão humana, validação pré-execução, execução e verificação.

Ações executáveis: `adjust_budget` e `pause_ad`, somente em modo SIMULADO (clientes de
demonstração; alteram apenas os registros demo no banco do Borges). Para clientes reais não
existe conector de escrita, então a execução é bloqueada e registrada como falha — nunca fingida.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    REC_ADJUST,
    REC_APPROVED,
    REC_AWAITING,
    REC_COMPLETED,
    REC_FAILED,
    REC_REJECTED,
    Ad,
    ApprovalDecision,
    Campaign,
    Client,
    Execution,
    Recommendation,
    User,
)
from app.services import audit

DECISIONS = {"approve": "approved", "reject": "rejected", "request_adjustment": "adjustment_requested"}


def decide(db: Session, rec: Recommendation, client: Client, user: User, decision: str, comment: str | None
           ) -> Recommendation:
    if rec.status not in (REC_AWAITING, REC_ADJUST):
        raise HTTPException(409, "Esta recomendação não está aguardando decisão.")
    if decision == "request_adjustment" and not (comment or "").strip():
        raise HTTPException(422, "Descreva o ajuste solicitado.")
    db.add(ApprovalDecision(recommendation_id=rec.id, client_id=client.id, user_id=user.id,
                            decision=DECISIONS[decision], comment=(comment or "").strip() or None))
    audit.record(db, action=f"recommendation.{DECISIONS[decision]}", actor=user, client_id=client.id,
                 entity_type="recommendation", entity_id=rec.id,
                 details={"title": rec.title, "comment": comment, "action_type": rec.action_type})
    if decision == "reject":
        rec.status = REC_REJECTED
    elif decision == "request_adjustment":
        rec.status = REC_ADJUST
    elif rec.action_type not in EXECUTORS or client.operation_level < 2:
        # Tarefa manual (análise, auditoria, criativo) ou cliente em nível consultivo: nada é executado.
        rec.status = REC_APPROVED
    else:
        EXECUTORS[rec.action_type](db, rec, client, user)
    db.flush()
    return rec


def execute_budget_change(db: Session, rec: Recommendation, client: Client, user: User) -> Execution:
    key = f"recommendation-{rec.id}"
    if db.scalar(select(Execution.id).where(Execution.idempotency_key == key)) is not None:
        raise HTTPException(409, "Esta recomendação já foi executada.")

    p = rec.action_payload
    campaign = db.get(Campaign, p.get("campaign_id"))
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> bool:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    simulated = client.data_mode == "demo"
    ok = check("Conector de escrita", simulated,
               "Execução simulada em dados demonstrativos." if simulated
               else "Não há conector de escrita autorizado para clientes reais (Fase 5).")
    ok &= check("Nível de operação", client.operation_level >= 2, f"Nível {client.operation_level} do cliente.")
    ok &= check("Conta correta", campaign is not None and campaign.client_id == client.id,
                "A campanha pertence a este cliente." if campaign and campaign.client_id == client.id
                else "Campanha inexistente ou de outro cliente.")
    if campaign is not None and campaign.client_id == client.id:
        current = float(campaign.daily_budget) if campaign.daily_budget is not None else None
        ok &= check("Estado atual confere", current == p.get("from"),
                    f"Orçamento atual {current}; recomendação calculada sobre {p.get('from')}.")
        limit = float(client.max_budget_change_pct)
        ok &= check("Limite financeiro", abs(p.get("change_pct", 1e9)) <= limit,
                    f"Variação de {p.get('change_pct')}% frente ao limite de {limit}% do cliente.")
        ok &= check("Valor válido", isinstance(p.get("to"), int | float) and p["to"] > 0,
                    f"Novo orçamento diário: {p.get('to')}.")
        ok &= check("Reversível", True, "O valor anterior fica registrado e pode ser restaurado.")

    execution = Execution(recommendation_id=rec.id, client_id=client.id, idempotency_key=key,
                          mode="simulated" if simulated else "live", status="executing", checks=checks)
    db.add(execution)
    if not ok:
        execution.status, rec.status = "failed", REC_FAILED
        execution.error = "; ".join(c["detail"] for c in checks if not c["passed"])
    else:
        execution.before_state = {"daily_budget": float(campaign.daily_budget)}
        campaign.daily_budget = Decimal(str(p["to"]))
        db.flush()
        db.refresh(campaign)  # leitura posterior: nenhuma alteração é concluída sem verificação
        execution.after_state = {"daily_budget": float(campaign.daily_budget)}
        execution.verified = float(campaign.daily_budget) == float(p["to"])
        execution.status = "completed" if execution.verified else "failed"
        rec.status = REC_COMPLETED if execution.verified else REC_FAILED
        if not execution.verified:
            execution.error = "A releitura não confirmou o novo valor."
    execution.finished_at = datetime.now(UTC)
    db.flush()
    audit.record(db, action=f"execution.{execution.status}", actor=user, client_id=client.id,
                 entity_type="execution", entity_id=execution.id,
                 details={"recommendation_id": rec.id, "mode": execution.mode, "campaign_id": p.get("campaign_id"),
                          "before": execution.before_state, "after": execution.after_state,
                          "verified": execution.verified, "error": execution.error})
    return execution


def execute_pause_ad(db: Session, rec: Recommendation, client: Client, user: User) -> Execution:
    key = f"recommendation-{rec.id}"
    if db.scalar(select(Execution.id).where(Execution.idempotency_key == key)) is not None:
        raise HTTPException(409, "Esta recomendação já foi executada.")
    ad = db.get(Ad, rec.action_payload.get("ad_id"))
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> bool:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    simulated = client.data_mode == "demo"
    ok = check("Conector de escrita", simulated,
               "Execução simulada em dados demonstrativos." if simulated
               else "Não há conector de escrita autorizado para clientes reais (Fase 5).")
    ok &= check("Nível de operação", client.operation_level >= 2, f"Nível {client.operation_level} do cliente.")
    own = ad is not None and ad.client_id == client.id
    ok &= check("Conta correta", own, "O anúncio pertence a este cliente." if own
                else "Anúncio inexistente ou de outro cliente.")
    if own:
        ok &= check("Estado atual confere", ad.status != "paused", f"Status atual do anúncio: {ad.status}.")
        ok &= check("Reversível", True, "O anúncio pode ser reativado; o status anterior fica registrado.")

    execution = Execution(recommendation_id=rec.id, client_id=client.id, idempotency_key=key,
                          mode="simulated" if simulated else "live", status="executing", checks=checks)
    db.add(execution)
    if not ok:
        execution.status, rec.status = "failed", REC_FAILED
        execution.error = "; ".join(c["detail"] for c in checks if not c["passed"])
    else:
        execution.before_state = {"ad_status": ad.status}
        ad.status = "paused"
        db.flush()
        db.refresh(ad)  # leitura posterior
        execution.after_state = {"ad_status": ad.status}
        execution.verified = ad.status == "paused"
        execution.status = "completed" if execution.verified else "failed"
        rec.status = REC_COMPLETED if execution.verified else REC_FAILED
        if not execution.verified:
            execution.error = "A releitura não confirmou o novo status."
    execution.finished_at = datetime.now(UTC)
    db.flush()
    audit.record(db, action=f"execution.{execution.status}", actor=user, client_id=client.id,
                 entity_type="execution", entity_id=execution.id,
                 details={"recommendation_id": rec.id, "mode": execution.mode, "action": "pause_ad",
                          "ad_id": rec.action_payload.get("ad_id"), "before": execution.before_state,
                          "after": execution.after_state, "verified": execution.verified, "error": execution.error})
    return execution


EXECUTORS = {"adjust_budget": execute_budget_change, "pause_ad": execute_pause_ad}
