"""Contrato dos conectores de dados. Cada integração (Windsor.ai, Meta, Google...) implementa esta
interface e é substituível sem tocar em agentes ou regras de negócio.

Leitura e escrita são contratos separados de propósito: ter um conector de leitura (ex.: Windsor.ai)
nunca implica permissão para alterar campanhas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class CampaignRecord:
    platform: str
    account_external_id: str
    account_name: str
    external_id: str
    name: str
    objective: str | None
    status: str
    daily_budget: Decimal | None
    currency: str | None = None


@dataclass(frozen=True)
class MetricRecord:
    campaign_external_id: str
    date: date
    spend: Decimal | None
    impressions: int | None
    reach: int | None
    clicks: int | None
    link_clicks: int | None
    leads: int | None
    attributed_purchases: int | None
    attributed_revenue: Decimal | None


@dataclass(frozen=True)
class SaleRecord:
    campaign_external_id: str
    date: date
    confirmed_sales: int
    confirmed_revenue: Decimal


@dataclass(frozen=True)
class AdSetRecord:
    """Conjunto de anúncios (Meta) ou grupo de anúncios (Google)."""

    campaign_external_id: str
    external_id: str
    name: str
    status: str | None = None


@dataclass(frozen=True)
class AdRecord:
    adset_external_id: str
    external_id: str
    name: str
    status: str | None = None


@dataclass(frozen=True)
class BreakdownRecord:
    """Fato diário no nível mais baixo disponível: anúncio (ad_external_id) ou conjunto (None).

    Alcance não entra aqui: não é somável entre anúncios nem entre dias.
    """

    campaign_external_id: str
    adset_external_id: str
    ad_external_id: str | None
    date: date
    spend: Decimal | None
    impressions: int | None
    clicks: int | None
    link_clicks: int | None
    leads: int | None
    attributed_purchases: int | None
    attributed_revenue: Decimal | None


@dataclass
class Payload:
    """Tudo que um conector entrega em uma sincronização."""

    campaigns: list[CampaignRecord] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)
    sales: list[SaleRecord] = field(default_factory=list)
    ad_sets: list[AdSetRecord] = field(default_factory=list)
    ads: list[AdRecord] = field(default_factory=list)
    breakdown: list[BreakdownRecord] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)  # problemas de qualidade detectados na origem


@dataclass(frozen=True)
class ConnectionStatus:
    ok: bool
    detail: str
    can_read: bool = False
    can_write: bool = False


class ReadConnector(Protocol):
    source: str  # rótulo gravado em cada linha de métrica
    sales_source: str | None  # None: o conector não fornece vendas confirmadas
    is_demo: bool

    def check(self) -> ConnectionStatus: ...
    def fetch(self, start: date, end: date) -> Payload: ...


class WriteConnector(Protocol):
    """Implementado apenas por conectores com escrita autorizada (Fase 5)."""

    def set_daily_budget(self, campaign_external_id: str, value: Decimal) -> None: ...
    def get_daily_budget(self, campaign_external_id: str) -> Decimal | None: ...
