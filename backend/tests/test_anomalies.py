from datetime import date, timedelta

from app.automation.anomalies import Day, campaign_anomalies, pacing_anomaly


def series(spends, leads=None):
    start = date(2026, 11, 1)
    leads = leads or [10] * len(spends)
    return [Day(start + timedelta(days=i), s, n) for i, (s, n) in enumerate(zip(spends, leads, strict=True))]


def kinds(findings):
    return sorted(f.kind for f in findings)


def test_stable_campaign_has_no_alerts():
    assert campaign_anomalies("C", series([100, 98, 103, 101, 99, 102, 100, 97, 101, 100, 99, 104, 98, 100, 101])) == []


def test_spend_spike_and_delivery_stop():
    base = [100, 98, 103, 101, 99, 102, 100, 97, 101, 100, 99, 104, 98, 100]
    # gasto saltou e os leads acompanharam: só o gasto é anomalia
    assert kinds(campaign_anomalies("C", series(base + [260], [10] * 14 + [26]))) == ["spend_spike"]
    # gasto saltou e os leads não acompanharam: o custo por lead também subiu
    assert kinds(campaign_anomalies("C", series(base + [260]))) == ["cpl_spike", "spend_spike"]
    assert kinds(campaign_anomalies("C", series(base + [0], [10] * 14 + [0]))) == ["delivery_stopped"]


def test_cpl_spike_needs_volume():
    spends = [100] * 17
    leads = [10] * 14 + [5, 4, 5]  # CPL de 10 para ~21
    assert kinds(campaign_anomalies("C", series(spends, leads))) == ["cpl_spike"]
    few = [10] * 14 + [1, 1, 1]  # só 3 leads recentes: não alerta
    assert campaign_anomalies("C", series(spends, few)) == []


def test_short_history_is_ignored_and_pacing():
    assert campaign_anomalies("C", series([100, 300])) == []
    assert pacing_anomaly(6000, 10_000, 10, 30).kind == "pacing_over"  # projeção 18.000
    assert pacing_anomaly(3000, 10_000, 10, 30) is None
    assert pacing_anomaly(None, 10_000, 10, 30) is None
