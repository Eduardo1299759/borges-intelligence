"""Conector de demonstração: gera um histórico determinístico e internamente consistente.

Os cenários foram desenhados para exercitar cada regra do motor de decisão. Tudo que sai daqui é
gravado com is_demo=True e source='demo_*' e nunca é apresentado como dado real.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.connectors.base import (
    AdRecord,
    AdSetRecord,
    BreakdownRecord,
    CampaignRecord,
    ConnectionStatus,
    MetricRecord,
    Payload,
    SaleRecord,
)

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

    def __init__(self, seed: str, today: date | None = None, currency: str = "BRL"):
        self.seed = seed
        self.currency = currency
        self.end = (today or date.today()) - timedelta(days=1)

    def check(self) -> ConnectionStatus:
        return ConnectionStatus(ok=True, detail="Gerador de dados demonstrativos.", can_read=True, can_write=False)

    def campaigns(self) -> list[CampaignRecord]:
        return [
            CampaignRecord(s.platform, *ACCOUNTS[s.platform], f"demo-{s.key}", s.name, s.objective, "active",
                           Decimal(str(s.daily_budget)), self.currency)
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

    def _structure(self) -> tuple[list[AdSetRecord], list[AdRecord],
                                  dict[str, list[tuple[str, str | None, float, float]]]]:
        """Conjuntos e anúncios de cada campanha, com a fração do resultado que cabe a cada um."""
        ad_sets: list[AdSetRecord] = []
        ads: list[AdRecord] = []
        shares: dict[str, list[tuple[str, str | None, float, float]]] = {}
        for s in SCENARIOS:
            cid = f"demo-{s.key}"
            # (nome, fração do investimento, fração dos resultados). "Imagem combo" gasta e não converte:
            # é o caso que o Meta Ads Specialist precisa encontrar.
            if s.platform == "meta":
                layout = [("Público amplo", [("Vídeo depoimento", 0.40, 0.52), ("Imagem oferta", 0.25, 0.28)]),
                          ("Interesses", [("Carrossel cardápio", 0.22, 0.20), ("Imagem combo", 0.13, 0.0)])]
            else:  # Google: o nível mais baixo aqui é o grupo de anúncios
                layout = [("Grupo principal", [(None, 0.65, 0.65)]), ("Grupo secundário", [(None, 0.35, 0.35)])]
            shares[cid] = []
            for i, (set_name, items) in enumerate(layout, 1):
                set_id = f"{cid}-set{i}"
                ad_sets.append(AdSetRecord(cid, set_id, set_name, "active"))
                for j, (ad_name, share, result_share) in enumerate(items, 1):
                    ad_id = f"{set_id}-ad{j}" if ad_name else None
                    if ad_id:
                        ads.append(AdRecord(set_id, ad_id, ad_name, "active"))
                    shares[cid].append((set_id, ad_id, share, result_share))
        return ad_sets, ads, shares

    def fetch(self, start: date, end: date) -> Payload:
        metrics, sales = self._generate()
        metrics = [m for m in metrics if start <= m.date <= end]
        sales = [r for r in sales if start <= r.date <= end]
        ad_sets, ads, shares = self._structure()
        breakdown: list[BreakdownRecord] = []
        for m in metrics:
            parts = shares[m.campaign_external_id]
            left = {f: getattr(m, f) for f in _SPLIT}
            # De trás para a frente: a sobra dos arredondamentos fica com o primeiro (maior) anúncio,
            # e um anúncio com fração zero de resultados recebe exatamente zero.
            for n, (set_id, ad_id, share, result_share) in reversed(list(enumerate(parts))):
                last = n == 0
                row = {}
                for f in _SPLIT:
                    total = getattr(m, f)
                    frac = result_share if f in _RESULTS else share
                    if isinstance(total, Decimal):
                        value = left[f] if last else (total * Decimal(str(frac))).quantize(Decimal("0.01"))
                    else:
                        value = left[f] if last else int(total * frac)
                    left[f] -= value  # o último recebe o resto: a soma fecha exatamente com a campanha
                    row[f] = value
                breakdown.append(BreakdownRecord(m.campaign_external_id, set_id, ad_id, m.date, **row))
        return Payload(campaigns=self.campaigns(), metrics=metrics, sales=sales, ad_sets=ad_sets, ads=ads,
                       breakdown=breakdown)


_SPLIT = ("spend", "impressions", "clicks", "link_clicks", "leads", "attributed_purchases", "attributed_revenue")
_RESULTS = {"leads", "attributed_purchases", "attributed_revenue"}
