"""Contratos tipados de entrada e saída da API."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginIn(BaseModel):
    # Texto simples: o login só compara com o cadastro; validar entregabilidade aqui barraria
    # domínios internos legítimos (ex.: admin@borges.local).
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    role: str


class ClientBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    segment: str | None = Field(default=None, max_length=120)
    business_goal: str | None = Field(default=None, max_length=2000)
    timezone: str = "America/Sao_Paulo"
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    monthly_budget: Decimal | None = Field(default=None, ge=0)
    target_cac: Decimal | None = Field(default=None, gt=0)
    target_roas: Decimal | None = Field(default=None, gt=0)
    gross_margin_pct: Decimal | None = Field(default=None, gt=0, le=100)
    # Nível 3 (autônomo limitado) só será habilitado quando houver execução real com limites (Fase 5).
    operation_level: Literal[1, 2] = 2
    max_budget_change_pct: Decimal = Field(default=Decimal("30"), ge=0, le=100)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Fuso horário inválido.") from exc
        return v


class ClientCreate(ClientBase):
    data_mode: Literal["demo", "live"] = "demo"


class ClientUpdate(ClientBase):
    pass


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_mode: str
    operation_level: int
    created_at: datetime


class AnalysisIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    days: int = Field(default=30, ge=7, le=90)


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "request_adjustment"]
    comment: str | None = Field(default=None, max_length=2000)


class DecisionOut(BaseModel):
    decision: str
    comment: str | None
    user: str | None
    created_at: datetime


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mode: str
    status: str
    checks: list[dict[str, Any]]
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    verified: bool
    error: str | None
    finished_at: datetime | None


class RecommendationOut(BaseModel):
    id: int
    client_id: int
    analysis_run_id: int
    campaign_id: int | None
    campaign_name: str | None
    platform: str | None
    agent: str
    rule: str
    title: str
    problem: str
    evidence: list[dict[str, Any]]
    probable_cause: str
    alternatives: list[str]
    hypothesis: str
    action_type: str
    action_payload: dict[str, Any]
    recommended_action: str
    expected_impact: str
    priority: str
    priority_score: int
    confidence: str
    risks: str
    requires_approval: bool
    validation_metric: str
    status: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    decisions: list[DecisionOut]
    executions: list[ExecutionOut]


class AnalysisOut(BaseModel):
    id: int
    question: str
    period_start: date
    period_end: date
    status: str
    is_demo: bool
    summary: dict[str, Any] | None
    created_at: datetime
    recommendations: list[RecommendationOut]


class WindsorKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=400)

    @field_validator("api_key")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if any(ch.isspace() for ch in v):
            raise ValueError("A chave não pode conter espaços.")
        return v


class AccountSelection(BaseModel):
    platform: Literal["meta", "google"]
    external_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)


class AccountsIn(BaseModel):
    accounts: list[AccountSelection] = Field(max_length=50)


class SyncIn(BaseModel):
    days: int = Field(default=30, ge=1, le=90)
