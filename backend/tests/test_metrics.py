"""Indicadores calculados à mão, para garantir que as fórmulas estão corretas."""
from datetime import date

import pytest

from app.services.metrics import Totals, compute_kpis, pct_change, previous_period


def test_kpis_match_hand_calculation():
    t = Totals(days=10, spend=1000, impressions=50_000, reach=40_000, clicks=1_000, link_clicks=800, leads=200,
               attributed_purchases=30, attributed_revenue=6_000, confirmed_sales=20, confirmed_revenue=4_000)
    k = compute_kpis(t, gross_margin_pct=40)
    assert k["ctr"] == pytest.approx(0.02)
    assert k["link_ctr"] == pytest.approx(0.016)
    assert k["cpc"] == pytest.approx(1.0)
    assert k["cpm"] == pytest.approx(20.0)
    assert k["avg_daily_frequency"] == pytest.approx(1.25)
    assert k["cpl"] == pytest.approx(5.0)
    assert k["real_cac"] == pytest.approx(50.0)  # investimento / vendas CONFIRMADAS
    assert k["attributed_cpa"] == pytest.approx(33.3333, rel=1e-4)
    assert k["confirmed_roas"] == pytest.approx(4.0)
    assert k["attributed_roas"] == pytest.approx(6.0)
    assert k["lead_to_sale_rate"] == pytest.approx(0.10)
    assert k["avg_ticket"] == pytest.approx(200.0)
    assert k["breakeven_roas"] == pytest.approx(2.5)  # 1 / 0,40
    assert k["max_sustainable_cac"] == pytest.approx(80.0)  # 200 x 0,40
    assert k["contribution_profit"] == pytest.approx(600.0)  # 4000 x 0,40 - 1000


def test_revenue_is_not_profit_without_margin():
    k = compute_kpis(Totals(days=1, spend=100, confirmed_sales=2, confirmed_revenue=500), gross_margin_pct=None)
    assert k["confirmed_roas"] == pytest.approx(5.0)
    assert k["contribution_profit"] is None
    assert k["breakeven_roas"] is None
    assert k["max_sustainable_cac"] is None


def test_unavailable_is_not_zero():
    k = compute_kpis(Totals(days=3, spend=300, impressions=1000, clicks=10, leads=5))
    assert k["confirmed_sales"] is None  # sem fonte de vendas: indisponível
    assert k["real_cac"] is None
    assert k["confirmed_roas"] is None
    zero = compute_kpis(Totals(days=3, spend=300, leads=5, confirmed_sales=0, confirmed_revenue=0))
    assert zero["confirmed_sales"] == 0  # zero real é preservado
    assert zero["real_cac"] is None  # divisão por zero não vira número
    assert zero["confirmed_roas"] == 0


def test_totals_addition_keeps_none_only_when_both_missing():
    s = Totals(spend=10, leads=None) + Totals(spend=5, leads=None, confirmed_sales=2)
    assert (s.spend, s.leads, s.confirmed_sales) == (15, None, 2)


def test_period_helpers():
    assert previous_period(date(2026, 3, 11), date(2026, 3, 20)) == (date(2026, 3, 1), date(2026, 3, 10))
    assert pct_change(120, 100) == pytest.approx(0.2)
    assert pct_change(50, 0) is None
    assert pct_change(None, 10) is None
