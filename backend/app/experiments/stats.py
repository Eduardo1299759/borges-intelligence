"""Estatística dos experimentos (funções puras).

Métrica de conversão: taxa clique → lead (leads / cliques), comparada entre controle e variante pelo teste
z de duas proporções. É a parte do custo por lead que depende do criativo; o custo do clique depende do
leilão e é reportado à parte (CPC), sem teste.

Limitações assumidas (e mostradas na tela):
- leads e cliques vêm da plataforma (atribuição dela), não do CRM;
- anúncios no mesmo conjunto disputam a mesma verba: a plataforma não sorteia o público como num A/B de
  verdade, então o resultado indica, mas não prova, causalidade. Para isso, use o teste A/B nativo da Meta.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Z_ALPHA = 1.959964  # bicaudal, 5%
Z_BETA = 0.841621  # poder de 80%


@dataclass
class Arm:
    spend: float
    impressions: float
    clicks: float
    leads: float

    @property
    def rate(self) -> float | None:
        return self.leads / self.clicks if self.clicks else None

    @property
    def cpl(self) -> float | None:
        return self.spend / self.leads if self.leads else None

    @property
    def cpc(self) -> float | None:
        return self.spend / self.clicks if self.clicks else None

    @property
    def ctr(self) -> float | None:
        return self.clicks / self.impressions if self.impressions else None


def normal_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2))


def two_proportion_test(x1: float, n1: float, x2: float, n2: float) -> tuple[float | None, float | None]:
    """Retorna (z, p-valor bicaudal) ou (None, None) se não há dados para testar."""
    if n1 <= 0 or n2 <= 0:
        return None, None
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (x2 / n2 - x1 / n1) / se
    return z, 2 * (1 - normal_cdf(abs(z)))


def sample_size_per_arm(baseline_rate: float, relative_mde: float) -> int | None:
    """Cliques por braço para detectar uma variação relativa `relative_mde` na taxa clique→lead
    (5% de significância, 80% de poder)."""
    if not 0 < baseline_rate < 1 or relative_mde <= 0:
        return None
    p1 = baseline_rate
    p2 = min(0.999, p1 * (1 + relative_mde))
    n = (Z_ALPHA + Z_BETA) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p2 - p1) ** 2
    return math.ceil(n)


@dataclass
class Verdict:
    status: str  # waiting_volume | significant_better | significant_worse | no_difference
    label: str
    z: float | None
    p_value: float | None
    lift: float | None  # variação relativa da taxa clique→lead da variante sobre o controle
    required_clicks: int | None


def evaluate(control: Arm, variant: Arm, relative_mde: float, duration_reached: bool = True) -> Verdict:
    """Só declara resultado quando o volume planejado OU a duração planejada foi atingido.

    Olhar o p-valor todo dia e parar no primeiro p < 5% ("espiar" o teste) multiplica os falsos vencedores;
    antes do ponto de decisão, um p < 5% é mostrado só como tendência.
    """
    lift = (variant.rate / control.rate - 1) if control.rate and variant.rate is not None else None
    required = sample_size_per_arm(control.rate, relative_mde) if control.rate else None
    z, p = two_proportion_test(control.leads, control.clicks, variant.leads, variant.clicks)
    enough = required is not None and min(control.clicks, variant.clicks) >= required
    decision_point = enough or duration_reached
    if p is not None and p < 0.05:
        better = z > 0
        if decision_point:
            return Verdict("significant_better" if better else "significant_worse",
                           "Variante melhor (significativo)" if better else "Variante pior (significativo)",
                           z, p, lift, required)
        return Verdict("trending_better" if better else "trending_worse",
                       "Tendência: variante melhor (aguardando volume)" if better
                       else "Tendência: variante pior (aguardando volume)", z, p, lift, required)
    if not decision_point:
        return Verdict("waiting_volume", "Aguardando volume", z, p, lift, required)
    if not enough:
        return Verdict("no_difference", "Sem diferença detectável (volume abaixo do planejado)", z, p, lift, required)
    return Verdict("no_difference", "Sem diferença detectável", z, p, lift, required)
