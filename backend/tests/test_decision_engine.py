"""Cada regra do motor de decisão, isolada, com números controlados."""
from app.decision.engine import AccountContext, CampaignSnapshot, evaluate, prioritize
from app.services.metrics import Totals, compute_kpis


def acc(**over) -> AccountContext:
    account = compute_kpis(Totals(days=30, spend=10_000, leads=2_000, confirmed_sales=400, confirmed_revenue=40_000))
    base = dict(target_cac=25.0, target_roas=4.0, margin_pct=35.0, max_budget_change_pct=30.0, kpis=account,
                period_label="2026-01-01 a 2026-01-30", sources="teste")
    return AccountContext(**{**base, **over})


def snap(half1: Totals | None = None, half2: Totals | None = None, budget: float | None = 100.0, **totals
         ) -> CampaignSnapshot:
    base = dict(days=30, spend=3000, impressions=150_000, reach=120_000, clicks=3000, leads=600,
                attributed_purchases=120, attributed_revenue=12_000, confirmed_sales=120, confirmed_revenue=12_000)
    t = Totals(**{**base, **totals})
    return CampaignSnapshot(1, "Campanha", "meta", budget, compute_kpis(t), compute_kpis(half1 or t),
                            compute_kpis(half2 or t), spend_share=0.3)


def test_healthy_campaign_is_kept_without_approval():
    d = evaluate(snap(), acc())  # CAC 25, ROAS 4 -> dentro da meta
    assert (d.rule, d.action_type, d.requires_approval) == ("keep", "no_change", False)


def test_small_sample_blocks_any_change_even_with_terrible_cac():
    d = evaluate(snap(days=30, leads=10, confirmed_sales=1, confirmed_revenue=50), acc())
    assert d.rule == "insufficient_sample" and d.action_type == "no_change"
    d = evaluate(snap(days=5), acc())
    assert d.rule == "insufficient_sample"


def test_tracking_divergence_takes_precedence_over_scaling():
    d = evaluate(snap(spend=1000, attributed_revenue=30_000), acc())  # ROAS confirmado 12, mas atribuição 2,5x
    assert d.rule == "tracking_divergence" and d.action_type == "tracking_audit"


def test_creative_fatigue():
    h1 = Totals(days=15, spend=1500, impressions=75_000, reach=60_000, clicks=1500, leads=300, confirmed_sales=60)
    h2 = Totals(days=15, spend=1500, impressions=75_000, reach=40_000, clicks=1000, leads=300, confirmed_sales=60)
    d = evaluate(snap(h1, h2), acc())
    assert d.rule == "creative_fatigue" and d.requires_approval


def test_ctr_drop_alone_is_not_fatigue():
    h1 = Totals(days=15, impressions=75_000, reach=60_000, clicks=1500)
    h2 = Totals(days=15, impressions=75_000, reach=60_000, clicks=1000)  # frequência estável
    assert evaluate(snap(h1, h2), acc()).rule == "keep"


def test_high_cac_with_cheap_low_quality_leads_asks_for_investigation_not_budget_cut():
    # CPL 3,33 (conta: 5,00); lead→venda 4% (conta: 20%); CAC 83
    d = evaluate(snap(leads=900, confirmed_sales=36, confirmed_revenue=3600, attributed_revenue=3600), acc())
    assert d.rule == "lead_quality" and d.action_type == "investigate_lead_quality"
    assert d.action_payload == {}


def test_high_cac_with_expensive_leads_reduces_budget_within_limit():
    d = evaluate(snap(leads=200, confirmed_sales=40, confirmed_revenue=4000, attributed_revenue=4000), acc())
    assert d.rule == "cac_above_target" and d.action_type == "adjust_budget"
    assert d.action_payload == {"campaign_id": 1, "from": 100.0, "to": 80.0, "change_pct": -20.0}
    capped = evaluate(snap(leads=200, confirmed_sales=40, confirmed_revenue=4000, attributed_revenue=4000),
                      acc(max_budget_change_pct=10.0))
    assert capped.action_payload["to"] == 90.0


def test_cac_slightly_above_target_is_tolerated():
    d = evaluate(snap(confirmed_sales=110, confirmed_revenue=12_000), acc())  # CAC 27,27 < 25 x 1,2
    assert d.rule == "keep"


def test_winner_is_scaled_gradually():
    d = evaluate(snap(spend=1500, confirmed_revenue=12_000, attributed_revenue=12_000), acc())  # ROAS 8, CAC 12,5
    assert d.rule == "scale_winner" and d.action_payload["to"] == 120.0


def test_budget_action_without_known_budget_becomes_manual():
    d = evaluate(snap(budget=None, spend=1500), acc())
    assert d.rule == "scale_winner" and d.action_type == "manual_review" and d.action_payload == {}


def test_without_targets_nothing_is_changed():
    d = evaluate(snap(leads=200, confirmed_sales=40, confirmed_revenue=4000, attributed_revenue=4000),
                 acc(target_cac=None, target_roas=None))
    assert d.rule == "keep" and d.alternatives


def test_prioritization_orders_by_financial_impact():
    s = snap(leads=200, confirmed_sales=40, confirmed_revenue=4000, attributed_revenue=4000)
    drafts = prioritize([evaluate(snap(), acc()), evaluate(s, acc())], {1: s})
    assert drafts[0].rule == "cac_above_target" and drafts[0].priority == "alta" and drafts[1].priority == "baixa"
