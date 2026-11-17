"""Conector Windsor.ai: transporte HTTP, normalização e reconciliação (sem rede)."""
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from app.connectors.base import BreakdownRecord, CampaignRecord, MetricRecord, Payload
from app.connectors.windsor import WindsorAuthError, WindsorClient, WindsorConnector, WindsorError
from app.services.ingestion import reconcile_levels
from tests.windsor_fake import (
    GOOGLE_A,
    META_A,
    META_OTHER,
    VALID_KEY,
    FakeWindsor,
    google_campaign_row,
    meta_campaign_row,
)

D1, D2 = date(2026, 11, 14), date(2026, 11, 15)
SECRET = "wk_super_secret_value_9876"


def client_with(handler, key=SECRET) -> WindsorClient:
    return WindsorClient(key, http=httpx.Client(transport=httpx.MockTransport(handler)),
                         base_url="https://windsor.test", sleep=lambda _: None)


# --- transporte -------------------------------------------------------------------------------------

def test_query_sends_expected_request_and_accepts_both_response_shapes():
    seen = []

    def handler(request):
        seen.append(request)
        body = {"data": [{"spend": 1}]} if len(seen) == 1 else [{"spend": 2}]
        return httpx.Response(200, json=body)

    c = client_with(handler)
    assert c.query("facebook", ["date", "spend"], D1, D2, ["1", "2"]) == [{"spend": 1}]
    assert c.query("google_ads", ["date"], D1, D2) == [{"spend": 2}]
    first = seen[0].url
    assert first.path == "/facebook"
    assert dict(first.params) == {"api_key": SECRET, "date_from": "2026-11-14", "date_to": "2026-11-15",
                                  "fields": "date,spend", "select_accounts": "1,2"}
    assert "select_accounts" not in seen[1].url.params


@pytest.mark.parametrize("status,body", [
    (400, {"error": "Not authorized", "code": "unauthorized"}),  # o que a API real devolve
    (401, {"error": {"code": "authentication_error", "message": "Invalid API key provided"}}),  # documentado
    (403, {"error": {"code": "permission_denied", "message": "x"}}),
])
def test_invalid_key_is_an_auth_error_and_is_not_retried(status, body):
    calls = []
    c = client_with(lambda r: calls.append(r) or httpx.Response(status, json=body))
    with pytest.raises(WindsorAuthError):
        c.query("facebook", ["date"], D1, D2)
    assert len(calls) == 1


def test_rate_limit_and_server_errors_are_retried_with_backoff():
    statuses = iter([429, 503, 200])
    waits = []
    c = WindsorClient(SECRET, base_url="https://windsor.test", sleep=waits.append, http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(next(statuses), json={"data": []}))))
    assert c.query("facebook", ["date"], D1, D2) == []
    assert waits == [2, 4]


def test_persistent_failures_raise_without_leaking_the_key():
    def boom(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    for handler in (boom, lambda r: httpx.Response(500, text="x"), lambda r: httpx.Response(400, text="bad field"),
                    lambda r: httpx.Response(200, text="<html>"), lambda r: httpx.Response(200, json={"data": "x"})):
        with pytest.raises(WindsorError) as err:
            client_with(handler).query("facebook", ["date"], D1, D2)
        assert SECRET not in str(err.value) and SECRET not in repr(err.value.__cause__)


# --- normalização -----------------------------------------------------------------------------------

def connector(fake: FakeWindsor, accounts=None, currency="BRL") -> WindsorConnector:
    accounts = accounts if accounts is not None else [{"platform": "meta", "external_id": META_A},
                                                      {"platform": "google", "external_id": GOOGLE_A}]
    return WindsorConnector(WindsorClient(VALID_KEY, http=fake.client(), base_url="https://windsor.test",
                                          sleep=lambda _: None), accounts, currency)


def fetch_two_days(fake=None, **kw) -> Payload:
    end = date.today() - timedelta(days=1)
    return connector(fake or FakeWindsor(), **kw).fetch(end - timedelta(days=1), end)


def test_meta_rows_are_normalized():
    p = fetch_two_days(accounts=[{"platform": "meta", "external_id": META_A}])
    assert [c.external_id for c in p.campaigns] == ["c-meta-1"]
    camp = p.campaigns[0]
    assert camp.daily_budget == Decimal("21.00")  # 2100 centavos
    assert (camp.status, camp.platform, camp.currency) == ("active", "meta", "BRL")
    assert len(p.metrics) == 2
    m = p.metrics[0]
    assert m.spend == Decimal("20.00") and m.reach == 800 and m.link_clicks == 12
    assert m.leads == 4  # conversas iniciadas contam como lead; actions_lead null = 0
    assert m.attributed_purchases == 0 and m.attributed_revenue == Decimal("0.00")  # null com entrega = zero
    assert {(s.external_id, s.name) for s in p.ad_sets} == {("as-1", "[Pub Frio]")}
    assert {a.external_id for a in p.ads} == {"ad-1", "ad-2"}
    ad2 = next(b for b in p.breakdown if b.ad_external_id == "ad-2")
    assert ad2.link_clicks == 0 and ad2.leads == 1 and ad2.spend == Decimal("5.50")


def test_rows_from_unselected_accounts_never_enter_the_payload():
    """A chave enxerga contas de outros clientes e o servidor falso ignora o filtro de contas."""
    p = fetch_two_days(accounts=[{"platform": "meta", "external_id": META_A}])
    assert all(c.account_external_id == META_A for c in p.campaigns)
    assert all(m.campaign_external_id == "c-meta-1" for m in p.metrics)
    assert all(b.campaign_external_id == "c-meta-1" for b in p.breakdown)
    assert sum(m.spend for m in p.metrics) == Decimal("40.00")  # nada dos 999,00 da outra conta
    assert any("contas não selecionadas" in i for i in p.issues)
    assert fetch_two_days(accounts=[]).metrics == []  # sem seleção, nada é sequer consultado


def test_google_rows_are_normalized():
    p = fetch_two_days(accounts=[{"platform": "google", "external_id": GOOGLE_A}])
    camp, m = p.campaigns[0], p.metrics[0]
    assert (camp.objective, camp.status, camp.daily_budget) == ("SEARCH", "active", None)
    assert m.spend == Decimal("19.40")  # 19,3987 arredondado para centavos
    assert m.leads == 2 and m.attributed_purchases is None and m.reach is None and m.link_clicks is None
    assert [b.ad_external_id for b in p.breakdown] == [None, None] and p.ads == []


def test_missing_delivery_stays_unavailable_not_zero():
    c = connector(FakeWindsor(), accounts=[{"platform": "meta", "external_id": META_A}])
    p = Payload()
    c._campaign_level(p, "meta", [meta_campaign_row(D1, spend=None, impressions=None, reach=None, clicks=None,
                                                    link_clicks=None,
                                                    actions_onsite_conversion_messaging_conversation_started_7d=None)])
    m = p.metrics[0]
    assert (m.spend, m.impressions, m.leads, m.attributed_revenue) == (None, None, None, None)


def test_renamed_campaign_is_merged_by_id_and_reported():
    c = connector(FakeWindsor(), accounts=[{"platform": "meta", "external_id": META_A}])
    p = Payload()
    c._campaign_level(p, "meta", [meta_campaign_row(D1, name="Nome antigo", spend=8.0, impressions=400),
                                  meta_campaign_row(D1, name="Nome novo", spend=12.0, impressions=600)])
    assert len(p.campaigns) == 1 and p.campaigns[0].name == "Nome novo"
    assert len(p.metrics) == 1 and p.metrics[0].spend == Decimal("20.00") and p.metrics[0].impressions == 1000
    assert any("mudaram de nome" in i for i in p.issues)


def test_account_in_another_currency_is_skipped_and_reported():
    c = connector(FakeWindsor(), accounts=[{"platform": "google", "external_id": GOOGLE_A}])
    p = Payload()
    c._campaign_level(p, "google", [google_campaign_row(D1, account_currency_code="USD")])
    c._breakdown(p, "google", [{"date": D1.isoformat(), "account_id": GOOGLE_A, "campaign_id": "9001",
                                "ad_group_id": "ag-1", "spend": 5}])
    assert p.campaigns == [] and p.metrics == [] and p.breakdown == []
    assert any("USD" in i and "moeda" in i for i in p.issues)


def test_check_and_account_discovery():
    c = connector(FakeWindsor(), accounts=[])
    status = c.check()
    assert status.ok and status.can_read and status.can_write is False
    found = c.discover_accounts()
    assert [(a["platform"], a["external_id"]) for a in found] == [
        ("google", GOOGLE_A), ("meta", META_OTHER), ("meta", META_A)]
    assert found[0]["name"] == GOOGLE_A  # conta sem nome usa o ID
    bad = WindsorConnector(WindsorClient("chave-errada", http=FakeWindsor().client(), base_url="https://w.test"), [])
    assert bad.check().ok is False


# --- reconciliação entre níveis ---------------------------------------------------------------------

def _payload(campaign_spend: str | None, parts: list[str]) -> Payload:
    blank = dict(impressions=None, clicks=None, link_clicks=None, leads=None, attributed_purchases=None,
                 attributed_revenue=None)
    return Payload(
        campaigns=[CampaignRecord("meta", "a", "A", "c1", "Campanha 1", None, "active", None)],
        metrics=[MetricRecord("c1", D1, Decimal(campaign_spend) if campaign_spend else None, reach=None, **blank),
                 MetricRecord("pmax", D1, Decimal("50"), reach=None, **blank)],
        breakdown=[BreakdownRecord("c1", "s1", f"ad{i}", D1, Decimal(v), **blank) for i, v in enumerate(parts)],
    )


def test_reconciliation_between_campaign_and_ad_level():
    assert reconcile_levels(_payload("100.00", ["60.00", "40.00"])) == []
    assert reconcile_levels(_payload("100.00", ["60.00", "39.50"])) == []  # dentro de 1%
    issues = reconcile_levels(_payload("100.00", ["60.00", "30.00"]))
    assert len(issues) == 1 and "Campanha 1" in issues[0] and "diverge" in issues[0]
    # campanha sem detalhamento (ex.: Performance Max) não é acusada
    assert reconcile_levels(_payload(None, [])) == []
    missing = _payload("100.00", ["100.00"])
    missing.metrics.append(MetricRecord("c1", D2, Decimal("80"), None, None, None, None, None, None, None))
    assert any("sem detalhamento" in i for i in reconcile_levels(missing))


def test_bad_request_surfaces_the_server_message_without_the_key():
    body = {"error": {"code": "invalid_request", "message": f"Unknown field foo (key {SECRET})"}}
    with pytest.raises(WindsorError) as err:
        client_with(lambda r: httpx.Response(400, json=body)).query("facebook", ["foo"], D1, D2)
    assert not isinstance(err.value, WindsorAuthError)
    assert "Unknown field foo" in str(err.value) and SECRET not in str(err.value)


def test_real_world_row_shapes_seen_in_production_accounts():
    """Formatos observados em contas reais (valores e nomes trocados)."""
    c = connector(FakeWindsor(), accounts=[{"platform": "meta", "external_id": META_A}])
    p = Payload()
    c._campaign_level(p, "meta", [
        # campanha pausada, sem entrega no dia, com compra atribuída tardiamente; orçamento no conjunto (null)
        meta_campaign_row(D1, campaign_id="late", campaign_status="PAUSED", campaign_daily_budget=None, spend=0,
                          impressions=0, reach=0, clicks=0, link_clicks=None, actions_purchase=1,
                          action_values_purchase=75.8,
                          actions_onsite_conversion_messaging_conversation_started_7d=None),
    ])
    camp, m = p.campaigns[0], p.metrics[0]
    assert (camp.status, camp.daily_budget) == ("paused", None)
    assert (m.spend, m.impressions) == (Decimal("0.00"), 0)  # zero real da plataforma é preservado
    assert (m.attributed_purchases, m.attributed_revenue) == (1, Decimal("75.80"))
    assert m.leads is None and m.link_clicks is None  # sem entrega, ação ausente continua indisponível
    # no nível de anúncio a API devolve 0 explícito (não null) para ações ausentes
    c._breakdown(p, "meta", [{"date": D1.isoformat(), "account_id": META_A, "campaign_id": "late", "adset_id": "s",
                              "adset_name": "CJ", "ad_id": "a", "ad_name": "AD", "spend": 0, "impressions": 0,
                              "clicks": 0, "link_clicks": 0, "actions_lead": 0,
                              "actions_onsite_conversion_messaging_conversation_started_7d": 0,
                              "actions_purchase": 1, "action_values_purchase": 75.8}])
    b = p.breakdown[0]
    assert (b.leads, b.attributed_purchases, b.attributed_revenue) == (0, 1, Decimal("75.80"))
    assert reconcile_levels(p) == []
