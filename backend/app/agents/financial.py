"""Agente 09 — Financial Intelligence (Fase 1: economia unitária da conta)."""
import calendar
from datetime import date
from typing import Any

from app.models import Client


def pacing(mtd_spend: float | None, monthly_budget: float | None, as_of: date) -> dict[str, Any]:
    """Ritmo de investimento no mês de `as_of`. Projeção linear simples: média diária x dias do mês."""
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    projected = None if mtd_spend is None else mtd_spend / as_of.day * days_in_month
    return {
        "month": as_of.strftime("%Y-%m"), "as_of": as_of.isoformat(), "days_elapsed": as_of.day,
        "days_in_month": days_in_month, "mtd_spend": mtd_spend, "monthly_budget": monthly_budget,
        "projected_spend": projected,
        "projected_vs_budget": None if projected is None or not monthly_budget else projected / monthly_budget - 1,
    }


def assess(kpis: dict[str, float | None], client: Client) -> dict[str, Any]:
    limitations: list[str] = []
    if client.gross_margin_pct is None:
        limitations.append("Margem não informada: ROAS de equilíbrio, CAC máximo e lucro não podem ser calculados.")
    if kpis.get("confirmed_sales") is None:
        limitations.append("Sem vendas confirmadas: a rentabilidade não pode ser avaliada com confiança.")
    limitations.append("LTV não é medido: o CAC máximo considera apenas a primeira compra.")
    limitations.append("O lucro de contribuição desconta apenas mídia; não inclui custos fixos nem honorários.")
    status = "unknown"
    cac, target = kpis.get("real_cac"), float(client.target_cac) if client.target_cac is not None else None
    if cac is not None and target is not None:
        status = "within_target" if cac <= target else "above_target"
    return {
        "real_cac": cac,
        "target_cac": target,
        "max_sustainable_cac": kpis.get("max_sustainable_cac"),
        "confirmed_roas": kpis.get("confirmed_roas"),
        "breakeven_roas": kpis.get("breakeven_roas"),
        "contribution_profit": kpis.get("contribution_profit"),
        "cac_status": status,
        "limitations": limitations,
    }
