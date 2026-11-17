"""Fluxo completo de um cliente real: conectar Windsor.ai, escolher contas, sincronizar, consultar."""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.connectors import windsor
from app.core import crypto
from app.models import BreakdownDaily, Campaign, Integration, MetricDaily, SalesDaily
from app.services import audit
from tests.conftest import login, make_user
from tests.windsor_fake import GOOGLE_A, META_A, VALID_KEY, FakeWindsor

ACCOUNTS = [{"platform": "meta", "external_id": META_A, "name": "CA Studio"},
            {"platform": "google", "external_id": GOOGLE_A, "name": "Studio Pilates"}]


@pytest.fixture()
def fake(monkeypatch) -> FakeWindsor:
    server = FakeWindsor()
    monkeypatch.setattr(windsor, "build_http_client", server.client)
    monkeypatch.setattr(windsor.time, "sleep", lambda _: None)
    return server


@pytest.fixture()
def live(admin) -> dict:
    r = admin.post("/api/clients", json={"name": "Studio Pilates", "data_mode": "live", "target_cac": "40",
                                         "monthly_budget": "1500"})
    assert r.status_code == 201
    return r.json()


def connect(http, cid, key=VALID_KEY, accounts=ACCOUNTS):
    r = http.put(f"/api/clients/{cid}/integration/windsor", json={"api_key": key})
    assert r.status_code == 200, r.text
    if accounts is not None:
        saved = http.put(f"/api/clients/{cid}/integration/windsor/accounts", json={"accounts": accounts})
        assert saved.status_code == 200
    return r.json()


def test_key_is_encrypted_at_rest_and_never_returned(admin, live, fake, db):
    out = connect(admin, live["id"])
    assert out["status"] == "connected" and out["key_hint"] == VALID_KEY[-4:] and "Leitura confirmada" in out["check"]
    stored = db.scalar(select(Integration))
    assert VALID_KEY not in stored.credentials_encrypted and crypto.decrypt(stored.credentials_encrypted) == VALID_KEY
    cid = live["id"]
    bodies = [admin.get(f"/api/clients/{cid}/integration").text, admin.get(f"/api/audit?client_id={cid}").text,
              admin.get(f"/api/clients/{cid}/sync-runs").text]
    assert all(VALID_KEY not in b for b in bodies)


def test_invalid_key_is_saved_as_error_not_as_connected(admin, live, fake):
    out = connect(admin, live["id"], key="chave-invalida-123", accounts=None)
    assert out["status"] == "error" and "recusou a chave" in out["last_error"]
    assert admin.get(f"/api/clients/{live['id']}/integration/windsor/accounts").status_code == 502


def test_missing_encryption_key_refuses_to_store_credentials(admin, live, fake, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "encryption_key", "")
    r = admin.put(f"/api/clients/{live['id']}/integration/windsor", json={"api_key": VALID_KEY})
    assert r.status_code == 503
    assert admin.get(f"/api/clients/{live['id']}/integration").json()["configured"] is False


def test_sync_requires_integration_and_selected_accounts(admin, live, fake):
    cid = live["id"]
    assert admin.post(f"/api/clients/{cid}/sync", json={"days": 7}).status_code == 409
    connect(admin, cid, accounts=None)
    r = admin.post(f"/api/clients/{cid}/sync", json={"days": 7})
    assert r.status_code == 409 and "Selecione" in r.json()["detail"]
    assert len(admin.get(f"/api/clients/{cid}/integration/windsor/accounts").json()) == 3


def test_full_sync_brings_real_data_only_for_selected_accounts(admin, live, fake, db):
    cid = live["id"]
    connect(admin, cid)
    run = admin.post(f"/api/clients/{cid}/sync", json={"days": 10}).json()
    assert run["status"] == "completed" and run["provider"] == "windsor"
    assert run["stats"] == {"campaigns": 2, "ad_sets": 2, "ads": 2, "metric_rows": 20, "breakdown_rows": 30,
                            "sales_rows": 0}
    assert any("contas não selecionadas" in i for i in run["issues"])
    assert not any("diverge" in i for i in run["issues"])  # anúncios fecham com a campanha

    names = set(db.scalars(select(Campaign.name).where(Campaign.client_id == cid)))
    assert names == {"[Studio] [Eng-WPP] [Pilates]", "[Studio] [Matriculas]"}  # nada da outra conta
    assert db.scalar(select(func.count()).select_from(MetricDaily).where(MetricDaily.is_demo)) == 0
    assert db.scalar(select(func.count()).select_from(SalesDaily)) == 0

    d = admin.get(f"/api/clients/{cid}/dashboard?days=7").json()
    assert d["is_demo"] is False and d["has_data"] and d["data_quality"]["sources"] == ["windsor"]
    k = d["kpis"]
    assert abs(k["spend"] - 7 * (20.00 + 19.40)) < 0.001 and k["leads"] == 7 * (4 + 2)
    # sem CRM: venda confirmada é INDISPONÍVEL, não zero
    assert k["confirmed_sales"] is None and k["real_cac"] is None and k["confirmed_roas"] is None
    assert any("vendas confirmadas" in i for i in d["data_quality"]["issues"])
    assert d["pacing"]["monthly_budget"] == 1500.0 and d["pacing"]["mtd_spend"] > 0

    camps = {c["platform"]: c for c in admin.get(f"/api/clients/{cid}/campaigns?days=7").json()["campaigns"]}
    assert camps["meta"]["daily_budget"] == 21.0 and camps["google"]["daily_budget"] is None
    meta = admin.get(f"/api/clients/{cid}/campaigns/{camps['meta']['id']}/breakdown?days=7").json()["ad_sets"]
    assert [s["name"] for s in meta] == ["[Pub Frio]"] and [a["name"] for a in meta[0]["ads"]] == [
        "[Ads - Vídeo]", "[Ads - Imagem]"]
    assert abs(meta[0]["kpis"]["spend"] - 7 * 20.0) < 0.001 and meta[0]["ads"][0]["kpis"]["leads"] == 21
    google = admin.get(f"/api/clients/{cid}/campaigns/{camps['google']['id']}/breakdown?days=7").json()["ad_sets"]
    assert google[0]["name"] == "[Pilates]" and google[0]["ads"] == []


def test_resync_is_idempotent_and_updates_values(admin, live, fake, db):
    cid = live["id"]
    connect(admin, cid)
    admin.post(f"/api/clients/{cid}/sync", json={"days": 10})
    before = (db.scalar(select(func.count()).select_from(MetricDaily)),
              db.scalar(select(func.count()).select_from(BreakdownDaily)))
    again = admin.post(f"/api/clients/{cid}/sync", json={"days": 10}).json()
    assert again["status"] == "completed"
    assert before == (db.scalar(select(func.count()).select_from(MetricDaily)),
                      db.scalar(select(func.count()).select_from(BreakdownDaily))) == (20, 30)
    assert len(admin.get(f"/api/clients/{cid}/sync-runs").json()) == 2


def test_failed_sync_is_recorded_and_keeps_previous_data(admin, live, fake, db):
    cid = live["id"]
    connect(admin, cid)
    admin.post(f"/api/clients/{cid}/sync", json={"days": 10})
    fake.fail_with = 500
    run = admin.post(f"/api/clients/{cid}/sync", json={"days": 10}).json()
    assert run["status"] == "failed" and "indisponível" in run["error"] and VALID_KEY not in run["error"]
    assert db.scalar(select(func.count()).select_from(MetricDaily)) == 20
    integ = admin.get(f"/api/clients/{cid}/integration").json()
    assert integ["status"] == "error" and integ["last_synced_at"] is not None
    d = admin.get(f"/api/clients/{cid}/dashboard").json()
    assert any("última sincronização falhou" in i for i in d["data_quality"]["issues"])
    assert admin.get(f"/api/audit?client_id={cid}").json()[0]["action"] == "sync.failed"
    assert audit.verify_chain(db)["valid"]


def test_analysis_on_live_data_does_not_invent_efficiency_conclusions(admin, live, fake):
    cid = live["id"]
    connect(admin, cid)
    admin.post(f"/api/clients/{cid}/sync", json={"days": 30})
    a = admin.post(f"/api/clients/{cid}/analyses", json={"question": "Como está o CAC?", "days": 30}).json()
    assert a["is_demo"] is False and "DEMONSTRATIVOS" not in a["summary"]["answer"]
    rules = {r["rule"] for r in a["recommendations"]}
    assert rules <= {"keep", "insufficient_sample", "creative_fatigue"}  # nenhuma regra de CAC/ROAS sem vendas
    assert all(not r["is_demo"] and all(e["source"] == "windsor" for e in r["evidence"]) for r in a["recommendations"])
    assert a["summary"]["finance"]["real_cac"] is None
    keep = next(r for r in a["recommendations"] if r["rule"] == "keep")
    assert any("Sem vendas confirmadas" in alt for alt in keep["alternatives"])


def test_integration_endpoints_respect_roles_isolation_and_demo(admin, live, fake, db, demo_client):
    cid = live["id"]
    make_user(db, "outro@example.com", "manager")
    other = login("outro@example.com")
    for method, path, body in (("get", "/integration", None), ("put", "/integration/windsor", {"api_key": VALID_KEY}),
                               ("get", "/integration/windsor/accounts", None), ("post", "/sync", {"days": 7}),
                               ("get", "/sync-runs", None), ("delete", "/integration/windsor", None),
                               ("get", "/campaigns/1/breakdown", None)):
        r = other.request(method.upper(), f"/api/clients/{cid}{path}", json=body)
        assert r.status_code == 404, path
    # cliente de demonstração não recebe credenciais reais, mas pode regenerar os dados demo
    demo_put = admin.put(f"/api/clients/{demo_client['id']}/integration/windsor", json={"api_key": VALID_KEY})
    assert demo_put.status_code == 409
    demo_run = admin.post(f"/api/clients/{demo_client['id']}/sync", json={"days": 30}).json()
    assert demo_run["status"] == "completed" and demo_run["provider"] == "demo_ads" and demo_run["issues"] == []
    # campanha de outro cliente não é acessível pelo detalhamento
    demo_campaign = admin.get(f"/api/clients/{demo_client['id']}/campaigns").json()["campaigns"][0]["id"]
    assert admin.get(f"/api/clients/{cid}/campaigns/{demo_campaign}/breakdown").status_code == 404
    own = admin.get(f"/api/clients/{demo_client['id']}/campaigns/{demo_campaign}/breakdown").json()
    assert len(own["ad_sets"]) == 2
    # remover a integração apaga a credencial e mantém o histórico
    connect(admin, cid)
    admin.post(f"/api/clients/{cid}/sync", json={"days": 7})
    assert admin.delete(f"/api/clients/{cid}/integration/windsor").status_code == 204
    assert db.scalar(select(func.count()).select_from(Integration)) == 0
    assert admin.get(f"/api/clients/{cid}/dashboard").json()["has_data"] is True


def test_demo_breakdown_sums_exactly_to_campaign(admin, demo_client, db):
    cid = demo_client["id"]
    end = date.today() - timedelta(days=1)
    for camp_id, spend, leads in db.execute(
        select(MetricDaily.campaign_id, func.sum(MetricDaily.spend), func.sum(MetricDaily.leads))
        .where(MetricDaily.client_id == cid, MetricDaily.date <= end).group_by(MetricDaily.campaign_id)
    ):
        detail = db.execute(select(func.sum(BreakdownDaily.spend), func.sum(BreakdownDaily.leads))
                            .where(BreakdownDaily.campaign_id == camp_id)).one()
        assert (float(detail[0]), detail[1]) == (float(spend), leads)


def test_installation_wide_account_allowlist(admin, live, fake, monkeypatch):
    """BORGES_WINDSOR_ALLOWED_ACCOUNTS restringe o que pode ser visto, escolhido e lido."""
    from app.core.config import get_settings
    cid = live["id"]
    connect(admin, cid)  # seleção feita antes de o escopo ser restringido
    monkeypatch.setattr(get_settings(), "windsor_allowed_accounts", f"{GOOGLE_A}, 999")
    found = admin.get(f"/api/clients/{cid}/integration/windsor/accounts").json()
    assert [a["external_id"] for a in found] == [GOOGLE_A]
    r = admin.put(f"/api/clients/{cid}/integration/windsor/accounts", json={"accounts": ACCOUNTS})
    assert r.status_code == 422 and META_A in r.json()["detail"]
    run = admin.post(f"/api/clients/{cid}/sync", json={"days": 5}).json()
    assert run["status"] == "completed" and run["stats"]["campaigns"] == 1  # só a conta Google permitida
