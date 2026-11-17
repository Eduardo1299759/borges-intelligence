"""Estatística dos experimentos conferida contra valores calculados à mão / tabelas conhecidas."""
import pytest

from app.experiments.stats import Arm, evaluate, normal_cdf, sample_size_per_arm, two_proportion_test


def test_normal_cdf_known_points():
    assert normal_cdf(0) == pytest.approx(0.5)
    assert normal_cdf(1.959964) == pytest.approx(0.975, abs=1e-6)


def test_two_proportion_test_matches_textbook_example():
    # 200/1000 vs 250/1000: p combinado 0,225; EP = sqrt(0,225*0,775*0,002) = 0,018675; z = 0,05/0,018675 = 2,6774
    z, p = two_proportion_test(200, 1000, 250, 1000)
    assert z == pytest.approx(2.6774, abs=1e-3) and p == pytest.approx(0.00742, abs=2e-4)
    assert two_proportion_test(0, 0, 5, 10) == (None, None)
    assert two_proportion_test(0, 10, 0, 10) == (None, None)  # sem variância


def test_sample_size():
    # taxa 10% -> 12%: (1,959964 + 0,841621)^2 x (0,09 + 0,1056) / 0,02^2 = 3838,1 -> 3839 cliques por braço
    assert sample_size_per_arm(0.10, 0.20) == 3839
    assert sample_size_per_arm(0.0, 0.2) is None and sample_size_per_arm(0.1, 0) is None


def test_evaluate_verdicts():
    control = Arm(spend=1000, impressions=100_000, clicks=4000, leads=400)
    better = Arm(spend=1000, impressions=100_000, clicks=4000, leads=500)
    v = evaluate(control, better, 0.2)
    assert v.status == "significant_better" and v.lift == pytest.approx(0.25) and v.p_value < 0.01
    worse = evaluate(control, Arm(1000, 100_000, 4000, 320), 0.2)
    assert worse.status == "significant_worse"
    small = evaluate(Arm(100, 10_000, 300, 30), Arm(100, 10_000, 300, 33), 0.2, duration_reached=False)
    assert small.status == "waiting_volume" and small.required_clicks == 3839
    same = evaluate(Arm(1000, 200_000, 5000, 500), Arm(1000, 200_000, 5000, 505), 0.2)
    assert same.status == "no_difference"
    assert Arm(100, 1000, 50, 0).cpl is None and Arm(100, 1000, 50, 5).cpl == 20


def test_no_peeking_before_the_decision_point():
    control = Arm(spend=400, impressions=22_000, clicks=405, leads=100)
    variant = Arm(spend=645, impressions=36_000, clicks=676, leads=212)  # p ~ 0,019, mas abaixo do volume
    early = evaluate(control, variant, 0.2, duration_reached=False)
    assert early.status == "trending_better" and early.p_value < 0.05 and early.required_clicks > 676
    at_end = evaluate(control, variant, 0.2, duration_reached=True)
    assert at_end.status == "significant_better"
    flat = evaluate(Arm(100, 10_000, 300, 30), Arm(100, 10_000, 300, 31), 0.2, duration_reached=True)
    assert flat.status == "no_difference" and "abaixo do planejado" in flat.label
