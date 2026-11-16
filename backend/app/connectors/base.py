"""Contrato dos conectores de dados. Cada integração (Windsor.ai, Meta, Google...) implementa esta
interface e é substituível sem tocar em agentes ou regras de negócio.

Leitura e escrita são contratos separados de propósito: ter um conector de leitura (ex.: Windsor.ai)
nunca implica permissão para alterar campanhas.
"""
from __future__ import annotations

from dataclasses import dataclass
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
class ConnectionStatus:
    ok: bool
    detail: str
    can_read: bool = False
    can_write: bool = False


class ReadConnector(Protocol):
    source: str
    is_demo: bool

    def check(self) -> ConnectionStatus: ...
    def campaigns(self) -> list[CampaignRecord]: ...
    def metrics(self, start: date, end: date) -> list[MetricRecord]: ...
    def sales(self, start: date, end: date) -> list[SaleRecord]: ...


class WriteConnector(Protocol):
    """Implementado apenas por conectores com escrita autorizada (Fase 5)."""

    def set_daily_budget(self, campaign_external_id: str, value: Decimal) -> None: ...
    def get_daily_budget(self, campaign_external_id: str) -> Decimal | None: ...
