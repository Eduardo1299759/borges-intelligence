"""Detecção de anomalias por campanha (funções puras sobre séries diárias).

Compara o último dia com dados (ou os últimos 3) com os 14 dias anteriores da própria campanha:
- spend_spike: investimento do dia acima da média + 3 desvios e acima de 150% da média;
- cpl_spike: custo por lead dos últimos 3 dias acima de 1,5x o dos 14 anteriores (com 5+ leads em cada janela);
- delivery_stopped: campanha que gastava (média de 14 dias acima de zero) e zerou no último dia;
- pacing_over: projeção do mês acima de 120% do orçamento mensal do cliente.
Limiares conservadores para não gerar alerta por oscilação normal.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date


@dataclass
class Day:
    date: date
    spend: float
    leads: float


@dataclass
class Finding:
    kind: str
    severity: str
    title: str
    detail: str
    evidence: dict


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def campaign_anomalies(name: str, series: list[Day]) -> list[Finding]:
    series = sorted(series, key=lambda d: d.date)
    if len(series) < 8:
        return []
    last, base = series[-1], series[-15:-1]
    out: list[Finding] = []
    spends = [d.spend for d in base]
    mean = statistics.fmean(spends)
    sd = statistics.pstdev(spends)
    if mean > 0 and last.spend > mean + 3 * sd and last.spend > 1.5 * mean:
        out.append(Finding("spend_spike", "alta", f"Gasto fora do padrão em “{name}”",
                           f"{_brl(last.spend)} em {last.date:%d/%m}, contra média de {_brl(mean)} nos 14 dias "
                           "anteriores. Confira mudanças de orçamento, lances ou público.",
                           {"day": str(last.date), "spend": last.spend, "mean_14d": round(mean, 2)}))
    if mean > 1 and last.spend == 0:
        out.append(Finding("delivery_stopped", "alta", f"Entrega parada em “{name}”",
                           f"Nenhum gasto em {last.date:%d/%m}; média de {_brl(mean)} por dia antes. Verifique "
                           "status, pagamento e reprovação de anúncios.",
                           {"day": str(last.date), "mean_14d": round(mean, 2)}))
    recent, before = series[-3:], series[-17:-3]
    r_spend, r_leads = sum(d.spend for d in recent), sum(d.leads for d in recent)
    b_spend, b_leads = sum(d.spend for d in before), sum(d.leads for d in before)
    if r_leads >= 5 and b_leads >= 5:
        r_cpl, b_cpl = r_spend / r_leads, b_spend / b_leads
        if r_cpl > 1.5 * b_cpl:
            out.append(Finding("cpl_spike", "media", f"Custo por lead subiu em “{name}”",
                               f"{_brl(r_cpl)} nos últimos 3 dias contra {_brl(b_cpl)} nos 14 dias anteriores.",
                               {"cpl_3d": round(r_cpl, 2), "cpl_14d": round(b_cpl, 2)}))
    return out


def pacing_anomaly(mtd_spend: float | None, monthly_budget: float | None, day_of_month: int,
                   days_in_month: int) -> Finding | None:
    if not mtd_spend or not monthly_budget or day_of_month < 3:
        return None
    projected = mtd_spend / day_of_month * days_in_month
    if projected > 1.2 * monthly_budget:
        return Finding("pacing_over", "media", "Ritmo de investimento acima do orçamento do mês",
                       f"Projeção de {_brl(projected)} para um orçamento de {_brl(monthly_budget)}.",
                       {"projected": round(projected, 2), "budget": monthly_budget})
    return None
