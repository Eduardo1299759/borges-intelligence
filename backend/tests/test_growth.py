"""Fase 4 pela API: Creative Studio, Experimentos e Radar competitivo."""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.ai import runner
from app.models import Ad, AIUsage, Campaign
from tests.conftest import login, make_user
from tests.test_ai import KEY, FakeAnthropic, enable


def campaign_ads(db, cid, name):
    camp = db.scalar(select(Campaign).where(Campaign.client_id == cid, Campaign.name == name))
    return {a.name: a.id for a in db.scalars(select(Ad).where(Ad.campaign_id == camp.id))}


# --- Creative Studio --------------------------------------------------------------------------------

def test_creative_library_classifies_demo_ads(admin, demo_client):
    lib = admin.get(f"/api/clients/{demo_client['id']}/creatives?days=30").json()
    assert lib["is_demo"] and len(lib["creatives"]) == 12  # 3 campanhas Meta x 4 anúncios; Google fica de fora
    combos = [c for c in lib["creatives"] if c["name"] == "Imagem combo"]
    assert {c["class"] for c in combos} == {"sem_resultado"} and all(c["leads"] == 0 for c in combos)
    winners = [c for c in lib["creatives"] if c["class"] == "vencedor"]
    assert winners and all(c["name"] == "Vídeo depoimento" for c in winners)
    fatigue = [c for c in lib["creatives"] if c["campaign"].startswith("Prospecção")]
    assert all(c["trend"] == "ctr_caindo" for c in fatigue if c["clicks"] > 0)  # campanha com fadiga no demo


def test_brief_without_ai_uses_template_and_no_numbers_are_invented(admin, demo_client, db):
    cid = demo_client["id"]
    ad_id = campaign_ads(db, cid, "Prospecção — Vídeo oferta combo")["Imagem combo"]
    r = admin.post(f"/api/clients/{cid}/briefs", json={
        "objective": "Mais pedidos pelo WhatsApp", "audience": "Moradores do bairro, 25-45",
        "offer": "Combo família com entrega grátis", "ad_id": ad_id})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["source"] == "modelo" and len(b["variations"]) == 3 and b["ai_model"] is None
    assert all("Combo família com entrega grátis" in v["primary_text"] for v in b["variations"])
    assert [x["id"] for x in admin.get(f"/api/clients/{cid}/briefs").json()] == [b["id"]]


def test_brief_with_ai_and_invented_price_is_rejected(admin, demo_client, db, monkeypatch):
    cid = demo_client["id"]
    enable(admin)

    def variations(facts, price=None):
        items = [{"name": f"V{i}", "angle": "Benefício", "test_hypothesis": "Hipótese", "format": "4:5",
                  "headline": "Combo família" + (f" por R$ {price}" if price else ""),
                  "primary_text": f"{facts['oferta']}.", "cta": "Pedir agora", "visual_brief": "Foto do combo"}
                 for i in range(4)]
        return json.dumps({"variations": items}), "end_turn"

    def brief_facts(kwargs_text):
        return json.loads(kwargs_text.split("Fatos (JSON):\n", 1)[1])

    class FakeBriefs(FakeAnthropic):
        def _create(self, **kwargs):
            self.calls.append(kwargs)
            facts = brief_facts(kwargs["messages"][0]["content"])
            text, stop = self.reply(facts)
            from types import SimpleNamespace
            return SimpleNamespace(model=kwargs["model"], stop_reason=stop, stop_details=None,
                                   content=[SimpleNamespace(type="text", text=text)],
                                   usage=SimpleNamespace(input_tokens=3000, output_tokens=1200))

    good = FakeBriefs(variations)
    monkeypatch.setattr(runner, "build_client", lambda key: good)
    body = {"objective": "Mais pedidos", "audience": "Famílias do bairro", "offer": "Combo família R$ 59,90"}
    b = admin.post(f"/api/clients/{cid}/briefs", json=body).json()
    assert b["source"] == "ia" and len(b["variations"]) == 4 and b["ai_model"] == "claude-opus-5-5"
    assert good.calls[0]["output_config"]["format"]["schema"]["required"] == ["variations"]

    invented = FakeBriefs(lambda f: variations(f, price="39,90"))  # preço que não está na oferta
    monkeypatch.setattr(runner, "build_client", lambda key: invented)
    b2 = admin.post(f"/api/clients/{cid}/briefs", json=body).json()
    assert b2["source"] == "modelo" and "39,90" in b2["note"]
    statuses = [u.status for u in db.scalars(select(AIUsage).order_by(AIUsage.id))]
    assert statuses == ["ok", "rejected_validation"]


def test_brief_rejects_ad_from_other_client(admin, demo_client, db):
    other = admin.post("/api/clients", json={"name": "Outro", "data_mode": "demo"}).json()
    foreign_ad = campaign_ads(db, other["id"], "Prospecção — Vídeo oferta combo")["Imagem combo"]
    r = admin.post(f"/api/clients/{demo_client['id']}/briefs", json={
        "objective": "x" * 5, "audience": "y" * 5, "offer": "z" * 5, "ad_id": foreign_ad})
    assert r.status_code == 404


# --- Experimentos -----------------------------------------------------------------------------------

def new_experiment(admin, cid, ads, **over):
    body = {"name": "Vídeo x imagem", "problem": "CPL alto no anúncio de imagem",
            "hypothesis": "Vídeo com depoimento converte mais clique em lead", "variable": "Formato do criativo",
            "control_ad_ids": [ads["Imagem oferta"]], "variant_ad_ids": [ads["Vídeo depoimento"]], **over}
    r = admin.post(f"/api/clients/{cid}/experiments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_experiment_lifecycle_with_retroactive_evaluation(admin, demo_client, db):
    cid = demo_client["id"]
    ads = campaign_ads(db, cid, "Conversas WhatsApp — Público aberto")
    e = new_experiment(admin, cid, ads)
    assert e["status"] == "draft" and e["evaluation"] is None and e["campaign_name"].startswith("Conversas")
    base = f"/api/clients/{cid}/experiments/{e['id']}"
    assert admin.post(f"{base}/conclude", json={"outcome": "success", "learning": "x" * 20}).status_code == 409
    start = (date.today() - timedelta(days=15)).isoformat()
    running = admin.post(f"{base}/start", json={"start_date": start}).json()
    assert running["status"] == "running" and running["retroactive"]
    ev = running["evaluation"]
    assert ev["window"]["days_with_data"] == 14
    # no demo, o vídeo recebe 52% dos leads com 40% da verba, e a imagem 28% com 25%: variante melhor
    assert ev["variant"]["lead_rate"] > ev["control"]["lead_rate"]
    assert ev["verdict"]["status"] in ("significant_better", "no_difference")  # duração planejada já atingida
    assert ev["verdict"]["required_clicks_per_arm"] > 0 and len(ev["notes"]) == 3
    done = admin.post(f"{base}/conclude", json={"outcome": "success",
                                                "learning": "Depoimento em vídeo converte melhor neste público."})
    out = done.json()
    assert out["status"] == "concluded" and out["outcome"] == "success" and out["evaluation"]["control"]
    assert admin.post(f"{base}/cancel").status_code == 409
    actions = [a["action"] for a in admin.get(f"/api/audit?client_id={cid}").json()]
    assert {"experiment.created", "experiment.started", "experiment.concluded"} <= set(actions)


def test_experiment_validation_and_isolation(admin, demo_client, db):
    cid = demo_client["id"]
    ads = campaign_ads(db, cid, "Conversas WhatsApp — Público aberto")
    other_campaign = campaign_ads(db, cid, "Remarketing — Cardápio digital")
    url = f"/api/clients/{cid}/experiments"
    base = {"name": "Teste", "problem": "abc", "hypothesis": "abc", "variable": "ab"}
    same = admin.post(url, json={**base, "control_ad_ids": [ads["Imagem oferta"]],
                                 "variant_ad_ids": [ads["Imagem oferta"]]})
    assert same.status_code == 422
    mixed = admin.post(url, json={**base, "control_ad_ids": [ads["Imagem oferta"]],
                                  "variant_ad_ids": [other_campaign["Vídeo depoimento"]]})
    assert mixed.status_code == 422 and "mesma campanha" in mixed.json()["detail"]
    e = new_experiment(admin, cid, ads)
    make_user(db, "intruso@example.com", "manager")
    intruso = login("intruso@example.com")
    assert intruso.get(f"{url}/{e['id']}").status_code == 404
    assert intruso.post(f"{url}/{e['id']}/start", json={}).status_code == 404


def test_experiment_waiting_for_data_when_started_today(admin, demo_client, db):
    cid = demo_client["id"]
    e = new_experiment(admin, cid, campaign_ads(db, cid, "Conversas WhatsApp — Público aberto"))
    out = admin.post(f"/api/clients/{cid}/experiments/{e['id']}/start", json={}).json()
    assert out["evaluation"]["verdict"]["status"] == "waiting_volume" and not out["retroactive"]


# --- Radar competitivo ------------------------------------------------------------------------------

def test_radar_manual_capture_and_rules_summary(admin, demo_client):
    cid = demo_client["id"]
    comp = admin.post(f"/api/clients/{cid}/competitors", json={"name": "Pizzaria Rival",
                                                               "website": "https://exemplo.test"}).json()
    seen = (date.today() - timedelta(days=40)).isoformat()
    r = admin.post(f"/api/clients/{cid}/competitors/{comp['id']}/ads", json={
        "ad_text": "Rodízio às quartas com refrigerante incluso", "offer": "Rodízio R$ 49,90", "format": "video",
        "first_seen": seen})
    assert r.status_code == 201
    future = admin.post(f"/api/clients/{cid}/competitors/{comp['id']}/ads", json={
        "ad_text": "abc def", "first_seen": (date.today() + timedelta(days=2)).isoformat()})
    assert future.status_code == 422
    radar = admin.get(f"/api/clients/{cid}/radar").json()
    assert radar["competitors"][0]["ads"] == 1 and radar["ads"][0]["days_running"] == 40
    ins = admin.post(f"/api/clients/{cid}/radar/insights").json()
    assert ins["source"] == "regras" and ins["offers"] == ["Pizzaria Rival: Rodízio R$ 49,90"]
    assert ins["long_running"][0]["days_running"] == 40
    assert admin.delete(f"/api/clients/{cid}/competitors/{comp['id']}").status_code == 204
    assert admin.get(f"/api/clients/{cid}/radar").json()["ads"] == []


def test_radar_ai_insights_never_claim_numbers_not_in_ads(admin, demo_client, monkeypatch):
    cid = demo_client["id"]
    comp = admin.post(f"/api/clients/{cid}/competitors", json={"name": "Rival"}).json()
    admin.post(f"/api/clients/{cid}/competitors/{comp['id']}/ads",
               json={"ad_text": "Entrega grátis acima de R$ 80,00", "offer": "Frete grátis"})
    enable(admin)

    def reply(price):
        def _r(facts):
            return json.dumps({"angles": [{"angle": "Frete grátis", "competitors": ["Rival"],
                                           "example": f"Entrega grátis acima de R$ {price}"}],
                               "offers": ["Frete grátis"], "opportunities": [
                                   {"idea": "Testar entrega grátis", "rationale": "Concorrente usa"}]}), "end_turn"
        return _r

    class FakeRadar(FakeAnthropic):
        def _create(self, **kwargs):
            from types import SimpleNamespace
            self.calls.append(kwargs)
            text, stop = self.reply(None)
            return SimpleNamespace(model=kwargs["model"], stop_reason=stop, stop_details=None,
                                   content=[SimpleNamespace(type="text", text=text)],
                                   usage=SimpleNamespace(input_tokens=2000, output_tokens=600))

    monkeypatch.setattr(runner, "build_client", lambda k: FakeRadar(reply("80,00")))
    ok = admin.post(f"/api/clients/{cid}/radar/insights").json()
    assert ok["source"] == "ia" and ok["angles"][0]["angle"] == "Frete grátis"
    monkeypatch.setattr(runner, "build_client", lambda k: FakeRadar(reply("120,00")))
    bad = admin.post(f"/api/clients/{cid}/radar/insights").json()
    assert bad["source"] == "regras" and "120,00" in bad["note"]


@pytest.mark.parametrize("path", ["creatives", "briefs", "experiments", "radar"])
def test_phase4_endpoints_are_isolated(admin, demo_client, db, path):
    make_user(db, "x@example.com", "manager")
    assert login("x@example.com").get(f"/api/clients/{demo_client['id']}/{path}").status_code == 404


def test_viewer_cannot_create(admin, demo_client, db):
    from app.models import User, UserClientAccess
    make_user(db, "leitor@example.com", "viewer")
    uid = db.scalar(select(User.id).where(User.email == "leitor@example.com"))
    db.add(UserClientAccess(user_id=uid, client_id=demo_client["id"]))
    db.commit()
    leitor = login("leitor@example.com")
    cid = demo_client["id"]
    assert leitor.get(f"/api/clients/{cid}/creatives").status_code == 200
    assert leitor.post(f"/api/clients/{cid}/competitors", json={"name": "Rival"}).status_code == 403
    assert leitor.post(f"/api/clients/{cid}/briefs", json={"objective": "abc", "audience": "abc",
                                                           "offer": "abc"}).status_code == 403
    _ = KEY  # mantém o import compartilhado com test_ai


def test_links_must_be_http(admin, demo_client):
    cid = demo_client["id"]
    assert admin.post(f"/api/clients/{cid}/competitors",
                      json={"name": "Rival", "website": "javascript:alert(1)"}).status_code == 422
    comp = admin.post(f"/api/clients/{cid}/competitors", json={"name": "Rival", "website": "rival.test"})
    assert comp.status_code == 422
    comp = admin.post(f"/api/clients/{cid}/competitors",
                      json={"name": "Rival", "website": " https://rival.test "}).json()
    bad = admin.post(f"/api/clients/{cid}/competitors/{comp['id']}/ads",
                     json={"ad_text": "texto", "url": "data:text/html,<script>alert(1)</script>"})
    assert bad.status_code == 422
    ok = admin.post(f"/api/clients/{cid}/competitors/{comp['id']}/ads", json={"ad_text": "texto", "url": ""})
    assert ok.status_code == 201
    assert admin.get(f"/api/clients/{cid}/radar").json()["competitors"][0]["website"] == "https://rival.test"
