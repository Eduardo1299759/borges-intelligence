"""Modelo de dados. Toda tabela de negócio carrega client_id: é a chave do isolamento entre clientes."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


Money = Numeric(14, 2)

ROLES = ("admin", "manager", "analyst", "viewer")
DATA_MODES = ("demo", "live")
PLATFORMS = ("meta", "google")

# Estados de uma recomendação (seção 12: estado de cada operação sempre visível).
REC_AWAITING = "awaiting_approval"
REC_INFO = "informational"  # recomendação de NÃO alterar; não exige aprovação
REC_ADJUST = "adjustment_requested"
REC_REJECTED = "rejected"
REC_APPROVED = "approved"  # aprovada; tarefa manual ou nível consultivo, sem execução automática
REC_EXECUTING = "executing"
REC_COMPLETED = "completed"
REC_FAILED = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    segment: Mapped[str | None] = mapped_column(String(120))
    business_goal: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    data_mode: Mapped[str] = mapped_column(String(10), default="demo")
    # Metas e economia unitária. None = não informado (nunca assumir zero).
    monthly_budget: Mapped[Decimal | None] = mapped_column(Money)
    target_cac: Mapped[Decimal | None] = mapped_column(Money)
    target_roas: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    gross_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Governança de execução (seção 10).
    operation_level: Mapped[int] = mapped_column(Integer, default=2)
    max_budget_change_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("30"))
    # Escrita real nas plataformas (via Windsor.ai). Desligada por padrão; só administradores ligam.
    write_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaigns: Mapped[list[Campaign]] = relationship(back_populates="client", cascade="all, delete-orphan")


class UserClientAccess(Base):
    __tablename__ = "user_client_access"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)


class AdAccount(Base):
    __tablename__ = "ad_accounts"
    __table_args__ = (UniqueConstraint("client_id", "platform", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("ad_account_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    ad_account_id: Mapped[int] = mapped_column(ForeignKey("ad_accounts.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(20))
    objective: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="active")
    daily_budget: Mapped[Decimal | None] = mapped_column(Money)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped[Client] = relationship(back_populates="campaigns")


class AdSet(Base):
    """Conjunto de anúncios (Meta) ou grupo de anúncios (Google)."""

    __tablename__ = "ad_sets"
    __table_args__ = (UniqueConstraint("campaign_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(20))


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (UniqueConstraint("ad_set_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    ad_set_id: Mapped[int] = mapped_column(ForeignKey("ad_sets.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(20))


class BreakdownDaily(Base):
    """Fato diário no nível mais baixo que a fonte entrega (anúncio na Meta, grupo no Google).

    A verdade para os indicadores da campanha continua sendo metric_daily; esta tabela detalha e é
    reconciliada contra ela a cada sincronização.
    """

    __tablename__ = "breakdown_daily"
    __table_args__ = (UniqueConstraint("entity_key", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    ad_set_id: Mapped[int] = mapped_column(ForeignKey("ad_sets.id", ondelete="CASCADE"), index=True)
    ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"))
    entity_key: Mapped[str] = mapped_column(String(40))  # "ad:<id>" ou "adset:<id>"
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    spend: Mapped[Decimal | None] = mapped_column(Money)
    impressions: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    link_clicks: Mapped[int | None] = mapped_column(Integer)
    leads: Mapped[int | None] = mapped_column(Integer)
    attributed_purchases: Mapped[int | None] = mapped_column(Integer)
    attributed_revenue: Mapped[Decimal | None] = mapped_column(Money)


class Integration(Base):
    """Credencial de uma fonte de dados para UM cliente. O segredo só existe cifrado (core/crypto.py)."""

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("client_id", "provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    credentials_encrypted: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(8))  # últimos 4 caracteres, para o usuário reconhecer a chave
    # Contas que ESTE cliente pode ler. Uma chave costuma dar acesso a contas de vários clientes.
    accounts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="untested")  # untested | connected | error
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | completed | failed
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetricDaily(Base):
    """Fato diário reportado pela plataforma de anúncios. Colunas nulas = dado indisponível, não zero."""

    __tablename__ = "metric_daily"
    __table_args__ = (UniqueConstraint("campaign_id", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    spend: Mapped[Decimal | None] = mapped_column(Money)
    impressions: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    link_clicks: Mapped[int | None] = mapped_column(Integer)
    leads: Mapped[int | None] = mapped_column(Integer)
    attributed_purchases: Mapped[int | None] = mapped_column(Integer)
    attributed_revenue: Mapped[Decimal | None] = mapped_column(Money)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SalesDaily(Base):
    """Vendas confirmadas (CRM/pedidos), separadas da receita atribuída pela plataforma."""

    __tablename__ = "sales_daily"
    __table_args__ = (UniqueConstraint("campaign_id", "date", "source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_sales: Mapped[int] = mapped_column(Integer)
    confirmed_revenue: Mapped[Decimal] = mapped_column(Money)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="running")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    ad_set_id: Mapped[int | None] = mapped_column(ForeignKey("ad_sets.id", ondelete="SET NULL"))
    ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="SET NULL"))
    agent: Mapped[str] = mapped_column(String(60))
    rule: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(240))
    problem: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    probable_cause: Mapped[str] = mapped_column(Text)
    alternatives: Mapped[list[str]] = mapped_column(JSON)
    hypothesis: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(40))
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    recommended_action: Mapped[str] = mapped_column(Text)
    expected_impact: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    priority_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str] = mapped_column(String(10))
    risks: Mapped[str] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_metric: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default=REC_AWAITING, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    campaign: Mapped[Campaign | None] = relationship()
    ad_set: Mapped[AdSet | None] = relationship()
    ad: Mapped[Ad | None] = relationship()
    decisions: Mapped[list[ApprovalDecision]] = relationship(order_by="ApprovalDecision.id")
    executions: Mapped[list[Execution]] = relationship(order_by="Execution.id")


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User | None] = relationship()


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    # Chave única: impede que a mesma recomendação seja executada duas vezes.
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    mode: Mapped[str] = mapped_column(String(20))  # simulated | live
    # executing | completed | failed | awaiting_confirmation | awaiting_verification
    status: Mapped[str] = mapped_column(String(30))
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    # Execução real: o que foi enviado à plataforma e a resposta (sem segredos).
    request: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Trilha de auditoria somente-inserção, encadeada por hash (ver services/audit.py)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[str] = mapped_column(String(40))  # ISO-8601 UTC como texto: entra no hash sem ambiguidade
    actor_user_id: Mapped[int | None] = mapped_column(Integer)
    actor_label: Mapped[str] = mapped_column(String(160))
    client_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class AISettings(Base):
    """Configuração da IA (Anthropic) da instalação. Linha única (id=1). A chave só existe cifrada."""

    __tablename__ = "ai_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    key_hint: Mapped[str | None] = mapped_column(String(8))
    model: Mapped[str] = mapped_column(String(60), default="claude-opus-5-5")
    effort: Mapped[str] = mapped_column(String(10), default="medium")
    monthly_cap_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("10"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AIUsage(Base):
    """Cada chamada (ou tentativa bloqueada) à IA, com tokens e custo em dólares."""

    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    purpose: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(60))
    # ok | refused | error | blocked_budget | rejected_validation
    status: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    detail: Mapped[str | None] = mapped_column(Text)


class Experiment(Base):
    """Teste A/B entre anúncios (controle x variante) de um cliente, do planejamento ao aprendizado."""

    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    brief_id: Mapped[int | None] = mapped_column(ForeignKey("creative_briefs.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    problem: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text)
    variable: Mapped[str] = mapped_column(String(200))
    primary_metric: Mapped[str] = mapped_column(String(30), default="lead_rate")
    guardrails: Mapped[list[str]] = mapped_column(JSON, default=list)
    control_ad_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    variant_ad_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    relative_mde_pct: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("20"))
    planned_days: Mapped[int] = mapped_column(Integer, default=14)
    start_date: Mapped[date | None] = mapped_column(Date)
    # draft | running | concluded | cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    outcome: Mapped[str | None] = mapped_column(String(20))  # success | failure | inconclusive
    learning: Mapped[str | None] = mapped_column(Text)
    final_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreativeBrief(Base):
    """Briefing de criativo com variações para teste. Gerado pela IA (se ativa) ou por modelo-padrão."""

    __tablename__ = "creative_briefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    ad_id: Mapped[int | None] = mapped_column(ForeignKey("ads.id", ondelete="SET NULL"))
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    objective: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text)
    offer: Mapped[str] = mapped_column(Text)
    angle: Mapped[str | None] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    variations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20))  # ia | modelo
    ai_model: Mapped[str | None] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Competitor(Base):
    __tablename__ = "competitors"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(300))
    facebook_page: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompetitorAd(Base):
    """Anúncio público de um concorrente. Fonte registrada: captura manual ou Biblioteca de Anúncios da Meta."""

    __tablename__ = "competitor_ads"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    url: Mapped[str | None] = mapped_column(String(500))
    ad_text: Mapped[str] = mapped_column(Text)
    offer: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(String(40))
    first_seen: Mapped[date | None] = mapped_column(Date)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LeadRecord(Base):
    """Lead vindo do CRM, sem dados pessoais. ref_hash é um identificador pseudonimizado (só para não duplicar
    na reimportação); nome, telefone, e-mail e documentos nunca são gravados."""

    __tablename__ = "lead_records"
    __table_args__ = (UniqueConstraint("client_id", "ref_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), index=True)
    ref_hash: Mapped[str] = mapped_column(String(64))
    date: Mapped[date] = mapped_column(Date, index=True)
    # novo | contato | qualificado | proposta | venda | perdido
    stage: Mapped[str] = mapped_column(String(20))
    response_minutes: Mapped[int | None] = mapped_column(Integer)
    lost_reason: Mapped[str | None] = mapped_column(String(200))
    value: Mapped[Decimal | None] = mapped_column(Money)
    source: Mapped[str] = mapped_column(String(30), default="crm_import")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportRun(Base):
    """Cada importação de planilha (pedidos ou leads), com o que entrou e o que ficou de fora."""

    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # orders | leads
    stats: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PageCheck(Base):
    """Verificação de uma página de destino (rastreamento, celular, velocidade)."""

    __tablename__ = "page_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Routine(Base):
    """Rotina automática de um cliente. Horários no fuso do cliente; next_run_at guardado em UTC."""

    __tablename__ = "routines"
    __table_args__ = (UniqueConstraint("client_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    # daily_audit | competitive_review | weekly_report | monthly_report | creative_review
    kind: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_type: Mapped[str] = mapped_column(String(20))  # daily | weekly | monthly | every_n_days
    time: Mapped[str] = mapped_column(String(5))  # HH:MM
    weekday: Mapped[int | None] = mapped_column(Integer)  # 0 = segunda
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    interval_days: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoutineRun(Base):
    __tablename__ = "routine_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey("routines.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | completed | failed
    triggered_by: Mapped[str] = mapped_column(String(160))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))  # alta | media | baixa
    title: Mapped[str] = mapped_column(String(240))
    detail: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | acknowledged | resolved
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # daily | weekly | monthly | competitive
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Learning(Base):
    """Memória de aprendizados. Só vira 'validated' com evidência de experimento; o resto é hipótese."""

    __tablename__ = "learnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    statement: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)  # segmento, campanha, público, oferta...
    # experiment | execution_impact | manual | platform_doc
    source_type: Mapped[str] = mapped_column(String(30))
    source_ref: Mapped[str | None] = mapped_column(String(80))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="hypothesis")  # hypothesis | validated | refuted
    reliability: Mapped[str] = mapped_column(String(10), default="baixa")  # baixa | média | alta
    created_by: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
