"""Conector de demonstração: gera um histórico determinístico e internamente consistente.

Os cenários foram desenhados para exercitar cada regra do motor de decisão. Tudo que sai daqui é
gravado com is_demo=True e source='demo_*' e nunca é apresentado como dado real.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.connectors.base import CampaignRecord, ConnectionStatus, MetricRecord, SaleRecord

HISTORY_DAYS = 90


@dataclass(frozen=True)
class Scenario:
    key: str
    platform: str
    name: str
    objective: str
    daily_budget: float
    cpm: float
    ctr: float
    link_share: float
    lead_rate: float  # leads por clique
    sale_rate: float  # vendas confirmadas por lead
    ticket: float
    attribution_factor: float = 1.0  # receita atribuída pela plataforma / receita confirmada
    frequency: float = 1.25
    fatigue: bool = False  # nos últimos 30 dias: CTR cai e frequência sobe
    started_days_ago: int = HISTORY_DAYS


SCENARIOS = [
    Scenario("wa_aberto", "meta", "Conversas WhatsApp — Público aberto", "Engajamento (conversas)",
             120, 18, 0.018, 0.85, 0.22, 0.08, 85),
    Scenario("rmk_cardapio", "meta", "Remarketing — Cardápio digital", "Vendas",
             60, 25, 0.030, 0.90, 0.30, 0.30, 85),
    Scenario("video_combo", "meta", "Prospecção — Vídeo oferta combo", "Vendas",
             90, 20, 0.022, 0.80, 0.20, 0.19, 85, fatigue=True),
    Scenario("search_marca", "google", "Search — Marca + Delivery", "Search",
             50, 50, 0.050, 1.0, 0.25, 0.20, 85),
    Scenario("pmax", "google", "Performance Max — Delivery", "Performance Max",
             100, 12, 0.012, 1.0, 0.10, 0.30, 85, attribution_factor=2.4),
    Scenario("search_generica", "google", "Search — Genéricas delivery (nova)", "Search",
             40, 45, 0.035, 1.0, 0.12, 0.20, 85, started_days_ago=5),
]

ACCOUNTS = {"meta": ("demo-act-meta", "Conta Meta (demonstração)"),
            "google": ("demo-act-google", "Conta Google Ads (demonstração)")}


def _stochastic_round(rng: random.Random, x: float) -> int:
    base = int(x)
    return base + (1 if rng.random() < x - base else 0)


class DemoConnector:
    source = "demo_ads"
    sales_source = "demo_crm"
    is_demo = True

    def __init__(self, seed: str, today: date | None = None):
        self.seed = seed
        self.end = (today or date.today()) - timedelta(days=1)

    def check(self) -> ConnectionStatus:
        return ConnectionStatus(ok=True, detail="Gerador de dados demonstrativos.", can_read=True, can_write=False)

    def campaigns(self) -> list[CampaignRecord]:
        return [
            CampaignRecord(s.platform, *ACCOUNTS[s.platform], f"demo-{s.key}", s.name, s.objective, "active",
                           Decimal(str(s.daily_budget)))
            for s in SCENARIOS
        ]

    def _generate(self) -> tuple[list[MetricRecord], list[SaleRecord]]:
        metrics: list[MetricRecord] = []
        sales: list[SaleRecord] = []
        for s in SCENARIOS:
            rng = random.Random(f"{self.seed}:{s.key}")
            for offset in range(min(s.started_days_ago, HISTORY_DAYS) - 1, -1, -1):
                day = self.end - timedelta(days=offset)
                weekend = 1.12 if day.weekday() >= 4 else 1.0
                ctr, freq = s.ctr, s.frequency
                if s.fatigue and offset < 30:
                    progress = (30 - offset) / 30
                    ctr = s.ctr * (1 - 0.50 * progress)
                    freq = s.frequency * (1 + 0.85 * progress)
                spend = s.daily_budget * rng.uniform(0.90, 1.0)
                impressions = int(spend / s.cpm * 1000 * rng.uniform(0.92, 1.08))
                clicks = _stochastic_round(rng, impressions * ctr * rng.uniform(0.88, 1.12))
                leads = _stochastic_round(rng, clicks * s.lead_rate * weekend * rng.uniform(0.85, 1.15))
                n_sales = _stochastic_round(rng, leads * s.sale_rate * rng.uniform(0.85, 1.15))
                revenue = round(n_sales * s.ticket * rng.uniform(0.92, 1.08), 2)
                metrics.append(MetricRecord(
                    campaign_external_id=f"demo-{s.key}", date=day,
                    spend=Decimal(f"{spend:.2f}"), impressions=impressions,
                    reach=max(1, int(impressions / freq)), clicks=clicks,
                    link_clicks=int(clicks * s.link_share), leads=leads,
                    attributed_purchases=_stochastic_round(rng, n_sales * s.attribution_factor),
                    attributed_revenue=Decimal(f"{revenue * s.attribution_factor:.2f}"),
                ))
                sales.append(SaleRecord(f"demo-{s.key}", day, n_sales, Decimal(f"{revenue:.2f}")))
        return metrics, sales

    def metrics(self, start: date, end: date) -> list[MetricRecord]:
        return [m for m in self._generate()[0] if start <= m.date <= end]

    def sales(self, start: date, end: date) -> list[SaleRecord]:
        return [r for r in self._generate()[1] if start <= r.date <= end]
