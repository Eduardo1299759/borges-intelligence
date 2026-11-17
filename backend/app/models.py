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
    status: Mapped[str] = mapped_column(String(20))
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
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
