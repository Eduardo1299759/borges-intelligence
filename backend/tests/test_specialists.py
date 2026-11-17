"""Especialistas Meta e Google: cada regra isolada, com números controlados."""
from app.decision.engine import AccountContext, CampaignSnapshot
from app.decision.specialists import EntityStats, evaluate_entities
from app.services.metrics import Totals, compute_kpis


def acc() -> AccountContext:
    return AccountContext(target_cac=25.0, target_roas=4.0, margin_pct=35.0, max_budget_change_pct=30.0,
                          kpis=compute_kpis(Totals(days=30, spend=10_000, leads=2_000)),
                          period_label="2026-01-01 a 2026-01-30", sources="teste")


def camp(platform="meta", spend=1000.0, leads=100, revenue=None) -> CampaignSnapshot:
    k = compute_kpis(Totals(days=30, spend=spend, leads=leads, attributed_revenue=revenue))
    return CampaignSnapshot(1, "Campanha X", platform, 50.0, k, k, k, spend_share=0.1)


def ad(i, spend, leads, status="active", set_id=1):
    return EntityStats(set_id, "Conjunto A", i, f"Anúncio {i}", status, spend, spend * 50, spend, leads)


def group(i, spend, leads):
    return EntityStats(i, f"Grupo {i}", None, None, "active", spend, spend * 50, spend, leads)


def rules(drafts):
    return sorted(d.rule for d in drafts)


def test_ad_spending_without_results_is_flagged_for_pause():
    # CPL da campanha = 10; anúncio 3 gastou 120 (12x) sem lead
    drafts = evaluate_entities(camp(), [ad(1, 600, 70), ad(2, 280, 30), ad(3, 120, 0)], acc())
    assert rules(drafts) == ["ad_no_results"]
    d = drafts[0]
    assert (d.action_type, d.action_payload, d.ad_id, d.ad_set_id) == ("pause_ad", {"ad_id": 3}, 3, 1)
    assert d.requires_approval and d.spend_share == 120 / 10_000
    assert "“Anúncio 3”" in d.title and "Campanha X" in d.title


def test_small_spend_without_results_is_noise_not_signal():
    # 25 de gasto = 2,5x o CPL: zero lead aqui ainda é compatível com o acaso
    assert evaluate_entities(camp(), [ad(1, 975, 100), ad(2, 25, 0)], acc()) == []


def test_already_paused_ad_is_only_reviewed():
    d = evaluate_entities(camp(), [ad(1, 880, 100), ad(2, 120, 0, status="paused")], acc())[0]
    assert d.action_type == "manual_review" and d.action_payload == {}


def test_no_ad_rules_when_campaign_has_too_few_leads():
    assert evaluate_entities(camp(leads=5), [ad(1, 500, 5), ad(2, 500, 0)], acc()) == []


def test_cpl_outlier():
    # CPL campanha 10; anúncio 2: 300/12 = 25 (2,5x), 30% do gasto
    drafts = evaluate_entities(camp(), [ad(1, 700, 88), ad(2, 300, 12)], acc())
    assert rules(drafts) == ["ad_cpl_outlier"] and drafts[0].ad_id == 2
    assert drafts[0].action_type == "creative_review" and drafts[0].action_payload == {}


def test_dilution_needs_many_tiny_ads():
    many = [ad(1, 500, 50), ad(2, 300, 30)] + [ad(i, 40, 4) for i in range(3, 8)]  # 5 de 7 com < 5%
    assert "ad_dilution" in rules(evaluate_entities(camp(spend=1000, leads=104), many, acc()))
    few = [ad(1, 500, 50), ad(2, 300, 30), ad(3, 200, 20)]
    assert evaluate_entities(camp(), few, acc()) == []


def test_google_groups_and_conversion_value():
    drafts = evaluate_entities(camp("google", revenue=0.0), [group(1, 880, 100), group(2, 120, 0)], acc())
    assert rules(drafts) == ["ad_no_results", "conversion_value_missing"]
    no_result = next(d for d in drafts if d.rule == "ad_no_results")
    assert no_result.action_type == "pause_ad_group" and no_result.action_payload == {"ad_set_id": 2}
    assert no_result.ad_id is None and no_result.ad_set_id == 2
    # receita indisponível (None) não é o mesmo que zero: não acusa
    assert rules(evaluate_entities(camp("google", revenue=None), [group(1, 1000, 100)], acc())) == []


def test_meta_rules_ignore_group_rows_and_vice_versa():
    assert evaluate_entities(camp("meta"), [group(1, 880, 100), group(2, 120, 0)], acc()) == []
    assert evaluate_entities(camp("google"), [ad(1, 880, 100), ad(2, 120, 0)], acc()) == []
