"""Agente 12 — Operations & Safety: decisão humana, validação pré-execução, execução e verificação.

Ações executáveis:
- adjust_budget   orçamento diário de campanha (Meta)
- pause_ad        pausar anúncio (Meta)
- pause_ad_group  pausar grupo de anúncios (Google)

Modo de execução:
- cliente de demonstração: SIMULADO (altera só os registros demo no banco do Borges);
- cliente real com escrita ligada (só administradores ligam): REAL, pelo Windsor.ai;
- cliente real sem escrita ligada: bloqueado e registrado como falha, nunca fingido.

Estados de uma execução: completed (verificada por releitura), awaiting_confirmation (a plataforma pediu
confirmação; exige uma segunda confirmação humana), awaiting_verification (aceita pela plataforma, mas a
releitura ainda não mostra a mudança), failed. Nenhuma mudança é dada como concluída sem verificação.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.windsor import WindsorError
from app.connectors.windsor_write import WindsorWriter
from app.core import crypto
from app.models import (
    REC_ADJUST,
    REC_APPROVED,
    REC_AWAITING,
    REC_COMPLETED,
    REC_EXECUTING,
    REC_FAILED,
    REC_REJECTED,
    Ad,
    AdAccount,
    AdSet,
    ApprovalDecision,
    Campaign,
    Client,
    Execution,
    Integration,
    Recommendation,
    User,
)
from app.services import audit

DECISIONS = {"approve": "approved", "reject": "rejected", "request_adjustment": "adjustment_requested"}
EXECUTABLE = ("adjust_budget", "pause_ad", "pause_ad_group")
PAUSED = {"paused", "campaign_paused", "adset_paused"}


def build_writer(db: Session, client: Client) -> WindsorWriter | None:
    integration = db.scalar(select(Integration).where(Integration.client_id == client.id,
                                                      Integration.provider == "windsor"))
    if integration is None:
        return None
    return WindsorWriter(crypto.decrypt(integration.credentials_encrypted))


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
    elif rec.action_type not in EXECUTABLE or client.operation_level < 2:
        # Tarefa manual (análise, auditoria, criativo) ou cliente em nível consultivo: nada é executado.
        rec.status = REC_APPROVED
    else:
        execute(db, rec, client, user)
    db.flush()
    return rec


@dataclass
class Plan:
    checks: list[dict[str, Any]] = field(default_factory=list)
    before: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    apply_local: Callable[[], None] | None = None
    platform: str | None = None
    account: str | None = None
    action: str | None = None
    params: dict[str, Any] | None = None
    read_back: Callable[[WindsorWriter], dict[str, Any]] | None = None

    def check(self, name: str, passed: bool, detail: str) -> bool:
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    @property
    def ok(self) -> bool:
        return all(c["passed"] for c in self.checks)


def _account(db: Session, campaign: Campaign) -> str:
    return db.get(AdAccount, campaign.ad_account_id).external_id


def plan_budget(db: Session, rec: Recommendation, client: Client) -> Plan:
    p, payload = Plan(), rec.action_payload
    campaign = db.get(Campaign, payload.get("campaign_id"))
    own = campaign is not None and campaign.client_id == client.id
    p.check("Conta correta", own,
            "A campanha pertence a este cliente." if own else "Campanha inexistente ou de outro cliente.")
    if not own:
        return p
    current = float(campaign.daily_budget) if campaign.daily_budget is not None else None
    p.check("Estado atual confere", current == payload.get("from"),
            f"Orçamento atual {current}; recomendação calculada sobre {payload.get('from')}.")
    limit = float(client.max_budget_change_pct)
    p.check("Limite financeiro", abs(payload.get("change_pct", 1e9)) <= limit,
            f"Variação de {payload.get('change_pct')}% frente ao limite de {limit}% do cliente.")
    target = payload.get("to")
    p.check("Valor válido", isinstance(target, int | float) and target > 0, f"Novo orçamento diário: {target}.")
    p.check("Reversível", True, "O valor anterior fica registrado e pode ser restaurado.")
    p.before, p.expected = {"daily_budget": current}, {"daily_budget": float(target or 0)}

    def apply_local() -> None:
        campaign.daily_budget = Decimal(str(target))
    p.apply_local = apply_local
    if campaign.platform == "meta":
        p.platform, p.account, p.action = "meta", _account(db, campaign), "set_campaign_budget"
        p.params = {"campaign_id": campaign.external_id, "budget_type": "daily",
                    "amount": int(round(float(target) * 100))}  # Meta: unidade mínima (centavos)
        p.read_back = lambda w: {"daily_budget": w.read_meta_campaign_budget(p.account, campaign.external_id)}
    return p


def plan_pause_ad(db: Session, rec: Recommendation, client: Client) -> Plan:
    p = Plan()
    ad = db.get(Ad, rec.action_payload.get("ad_id"))
    own = ad is not None and ad.client_id == client.id
    p.check("Conta correta", own,
            "O anúncio pertence a este cliente." if own else "Anúncio inexistente ou de outro cliente.")
    if not own:
        return p
    p.check("Estado atual confere", ad.status != "paused", f"Status atual do anúncio: {ad.status}.")
    p.check("Reversível", True, "O anúncio pode ser reativado; o status anterior fica registrado.")
    p.before, p.expected = {"ad_status": ad.status}, {"ad_status": "paused"}

    def apply_local() -> None:
        ad.status = "paused"
    p.apply_local = apply_local
    campaign = db.get(Campaign, ad.campaign_id)
    p.platform, p.account, p.action = "meta", _account(db, campaign), "pause_ad"
    p.params = {"ad_id": ad.external_id}

    def read_back(w: WindsorWriter) -> dict[str, Any]:
        status = w.read_meta_ad_status(p.account, ad.external_id)
        return {"ad_status": "paused" if status in PAUSED else status}
    p.read_back = read_back
    return p


def plan_pause_ad_group(db: Session, rec: Recommendation, client: Client) -> Plan:
    p = Plan()
    group = db.get(AdSet, rec.action_payload.get("ad_set_id"))
    own = group is not None and group.client_id == client.id
    p.check("Conta correta", own,
            "O grupo pertence a este cliente." if own else "Grupo inexistente ou de outro cliente.")
    if not own:
        return p
    p.check("Estado atual confere", group.status != "paused", f"Status atual do grupo: {group.status}.")
    p.check("Reversível", True, "O grupo pode ser reativado; o status anterior fica registrado.")
    p.before, p.expected = {"ad_group_status": group.status}, {"ad_group_status": "paused"}

    def apply_local() -> None:
        group.status = "paused"
    p.apply_local = apply_local
    campaign = db.get(Campaign, group.campaign_id)
    p.platform, p.account, p.action = "google", _account(db, campaign), "pause_ad_group"
    p.params = {"ad_group_id": group.external_id}
    p.read_back = lambda w: {"ad_group_status": w.read_google_ad_group_status(p.account, group.external_id)}
    return p


PLANNERS = {"adjust_budget": plan_budget, "pause_ad": plan_pause_ad, "pause_ad_group": plan_pause_ad_group}


def _finish(db: Session, rec: Recommendation, execution: Execution, client: Client, user: User) -> None:
    rec.status = {"completed": REC_COMPLETED, "failed": REC_FAILED}.get(execution.status, REC_EXECUTING)
    if execution.status in ("completed", "failed"):
        execution.finished_at = datetime.now(UTC)
    db.flush()
    audit.record(db, action=f"execution.{execution.status}", actor=user, client_id=client.id,
                 entity_type="execution", entity_id=execution.id,
                 details={"recommendation_id": rec.id, "mode": execution.mode, "action": rec.action_type,
                          "before": execution.before_state, "after": execution.after_state,
                          "request": execution.request, "verified": execution.verified, "error": execution.error})


def _verify(db: Session, plan: Plan, execution: Execution, writer: WindsorWriter) -> None:
    try:
        seen = plan.read_back(writer) if plan.read_back else None
    except WindsorError as exc:
        seen, execution.error = None, f"Releitura falhou: {exc}"
    if seen is not None and seen == plan.expected:
        execution.after_state, execution.verified, execution.status, execution.error = seen, True, "completed", None
        plan.apply_local()
    else:
        execution.after_state = seen
        execution.status = "awaiting_verification"
        execution.error = execution.error or ("A plataforma aceitou a mudança, mas os dados do Windsor.ai ainda não a "
                                              "mostram (cache). Use 'Verificar agora' mais tarde.")


def execute(db: Session, rec: Recommendation, client: Client, user: User) -> Execution:
    key = f"recommendation-{rec.id}"
    if db.scalar(select(Execution.id).where(Execution.idempotency_key == key)) is not None:
        raise HTTPException(409, "Esta recomendação já foi executada.")
    plan = PLANNERS[rec.action_type](db, rec, client)
    simulated = client.data_mode == "demo"
    live_ready = client.data_mode == "live" and client.write_enabled
    plan.checks.insert(0, {"check": "Conector de escrita",
                           "passed": simulated or (live_ready and plan.action is not None),
                           "detail": "Execução simulada em dados demonstrativos." if simulated else
                           ("Escrita real pelo Windsor.ai." if live_ready and plan.action else
                            "Escrita real desligada para este cliente (Clientes e contas, só administradores)."
                            if not client.write_enabled else "Esta ação não tem escrita disponível nesta plataforma.")})
    plan.checks.insert(1, {"check": "Nível de operação", "passed": client.operation_level >= 2,
                           "detail": f"Nível {client.operation_level} do cliente."})
    writer = None
    if not simulated and plan.ok:
        try:
            writer = build_writer(db, client)
        except crypto.EncryptionUnavailable as exc:
            plan.check("Credencial do Windsor.ai", False, str(exc))
        if writer is None and plan.ok:
            plan.check("Credencial do Windsor.ai", False, "Integração Windsor.ai não configurada para este cliente.")

    execution = Execution(recommendation_id=rec.id, client_id=client.id, idempotency_key=key,
                          mode="simulated" if simulated else "live", status="executing", checks=plan.checks,
                          before_state=plan.before)
    db.add(execution)
    db.flush()
    if not plan.ok:
        execution.status = "failed"
        execution.error = "; ".join(c["detail"] for c in plan.checks if not c["passed"])
    elif simulated:
        plan.apply_local()
        db.flush()
        execution.after_state = plan.expected  # releitura do registro demo, já gravado
        execution.verified, execution.status = True, "completed"
    else:
        execution.request = {"platform": plan.platform, "account": plan.account, "action": plan.action,
                             "params": plan.params}
        outcome = writer.execute(plan.platform, plan.account, plan.action, plan.params)
        execution.response = {"detail": outcome.detail, **outcome.response}
        if outcome.status == "failed":
            execution.status, execution.error = "failed", outcome.detail
        elif outcome.status == "needs_confirmation":
            execution.status = "awaiting_confirmation"
            execution.response = {"detail": outcome.detail, "confirmation_token": outcome.confirmation_token}
        else:
            _verify(db, plan, execution, writer)
    _finish(db, rec, execution, client, user)
    return execution


def _execution_for(db: Session, client: Client, execution_id: int) -> tuple[Execution, Recommendation]:
    execution = db.get(Execution, execution_id, with_for_update=True)
    if execution is None or execution.client_id != client.id:
        raise HTTPException(404, "Execução não encontrada.")
    return execution, db.get(Recommendation, execution.recommendation_id)


def confirm(db: Session, client: Client, user: User, execution_id: int) -> Execution:
    """Segunda confirmação humana quando a plataforma pediu (ex.: aumento de gasto)."""
    execution, rec = _execution_for(db, client, execution_id)
    if execution.status != "awaiting_confirmation":
        raise HTTPException(409, "Esta execução não está aguardando confirmação.")
    plan = PLANNERS[rec.action_type](db, rec, client)
    writer = build_writer(db, client)
    if writer is None or not client.write_enabled:
        raise HTTPException(409, "Escrita real indisponível para este cliente.")
    token = (execution.response or {}).get("confirmation_token")
    outcome = writer.execute(plan.platform, plan.account, plan.action, plan.params, confirmation_token=token)
    execution.response = {"detail": outcome.detail, **outcome.response}
    if outcome.status != "accepted":
        execution.status, execution.error = "failed", outcome.detail
    else:
        _verify(db, plan, execution, writer)
    audit.record(db, action="execution.confirmed", actor=user, client_id=client.id, entity_type="execution",
                 entity_id=execution.id, details={"recommendation_id": rec.id})
    _finish(db, rec, execution, client, user)
    return execution


def verify(db: Session, client: Client, user: User, execution_id: int) -> Execution:
    execution, rec = _execution_for(db, client, execution_id)
    if execution.status != "awaiting_verification":
        raise HTTPException(409, "Esta execução não está aguardando verificação.")
    writer = build_writer(db, client)
    if writer is None:
        raise HTTPException(409, "Integração Windsor.ai não configurada.")
    plan = PLANNERS[rec.action_type](db, rec, client)
    _verify(db, plan, execution, writer)
    _finish(db, rec, execution, client, user)
    return execution
