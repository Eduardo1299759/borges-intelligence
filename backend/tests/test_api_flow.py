"""Fluxos completos pela API: autenticação, isolamento, análise, aprovação, execução e auditoria."""
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.main import app
from app.models import AuditLog, Campaign, MetricDaily, Recommendation
from app.services import audit
from tests.conftest import DEMO_CLIENT, login, make_user


def analyze(http, client_id, question="Como está o CAC das campanhas?"):
    r = http.post(f"/api/clients/{client_id}/analyses", json={"question": question, "days": 30})
    assert r.status_code == 201, r.text
    return r.json()


def by_rule(analysis):
    return {r["rule"]: r for r in analysis["recommendations"]}


# --- autenticação ---------------------------------------------------------------------------------

def test_auth_required_and_login_flow(db):
    make_user(db, "ana@example.com", "manager")
    anon = TestClient(app)
    assert anon.get("/api/clients").status_code == 401
    assert anon.get("/api/auth/me").status_code == 401
    bad = anon.post("/api/auth/login", json={"email": "ana@example.com", "password": "errada"})
    assert bad.status_code == 401
    assert anon.post("/api/auth/login", json={"email": "x@example.com", "password": "errada"}).json() == bad.json()
    http = login("ana@example.com")
    assert http.get("/api/auth/me").json()["role"] == "manager"
    again = http.post("/api/auth/login", json={"email": "ana@example.com", "password": "senha-de-teste-123"})
    assert "httponly" in again.headers["set-cookie"].lower()
    http.post("/api/auth/logout")
    assert http.get("/api/auth/me").status_code == 401
    make_user(db, "admin@borges.local", "admin")  # domínio interno precisa conseguir entrar
    assert login(" Admin@Borges.local ").get("/api/auth/me").json()["email"] == "admin@borges.local"


# --- clientes e isolamento -------------------------------------------------------------------------

def test_client_isolation_between_users(db):
    make_user(db, "a@example.com", "manager")
    make_user(db, "b@example.com", "manager")
    a, b = login("a@example.com"), login("b@example.com")
    ca = a.post("/api/clients", json=DEMO_CLIENT).json()
    cb = b.post("/api/clients", json={**DEMO_CLIENT, "name": "Cliente de B"}).json()
    assert [c["id"] for c in a.get("/api/clients").json()] == [ca["id"]]
    rec_b = by_rule(analyze(b, cb["id"]))["scale_winner"]
    for path in ("", "/dashboard", "/campaigns", "/analyses", "/recommendations"):
        assert a.get(f"/api/clients/{cb['id']}{path}").status_code == 404, path
    assert a.put(f"/api/clients/{cb['id']}", json=DEMO_CLIENT).status_code == 404
    assert a.post(f"/api/clients/{cb['id']}/analyses", json={"question": "teste"}).status_code == 404
    # Recomendação de B não pode ser decidida por A, nem "por dentro" do próprio cliente de A.
    for cid in (cb["id"], ca["id"]):
        r = a.post(f"/api/clients/{cid}/recommendations/{rec_b['id']}/decision", json={"decision": "approve"})
        assert r.status_code == 404
    assert a.get(f"/api/audit?client_id={cb['id']}").json() == []
    assert all(e["client_id"] == ca["id"] for e in a.get("/api/audit").json())


def test_roles(db, admin, demo_client):
    make_user(db, "viewer@example.com", "viewer")
    make_user(db, "analyst@example.com", "analyst")
    from app.models import User, UserClientAccess
    for email in ("viewer@example.com", "analyst@example.com"):
        uid = db.scalar(select(User.id).where(User.email == email))
        db.add(UserClientAccess(user_id=uid, client_id=demo_client["id"]))
    db.commit()
    viewer, analyst = login("viewer@example.com"), login("analyst@example.com")
    cid = demo_client["id"]
    assert viewer.get(f"/api/clients/{cid}/dashboard").status_code == 200
    assert viewer.post("/api/clients", json=DEMO_CLIENT).status_code == 403
    assert viewer.post(f"/api/clients/{cid}/analyses", json={"question": "teste"}).status_code == 403
    rec = by_rule(analyze(analyst, cid))["scale_winner"]
    r = analyst.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 403
    assert analyst.get("/api/audit/verify").status_code == 403


def test_client_validation(admin):
    for bad in ({"name": "X"}, {"name": "Ok", "gross_margin_pct": "140"}, {"name": "Ok", "timezone": "Marte/Base"},
                {"name": "Ok", "operation_level": 3}, {"name": "Ok", "target_cac": "0"}):
        assert admin.post("/api/clients", json=bad).status_code == 422, bad


# --- dados demonstrativos e indicadores ------------------------------------------------------------

def test_demo_dashboard_is_flagged_and_consistent(admin, demo_client, db):
    d = admin.get(f"/api/clients/{demo_client['id']}/dashboard?days=30").json()
    assert d["is_demo"] is True and d["has_data"] is True
    assert set(d["data_quality"]["sources"]) == {"demo_ads", "demo_crm"}
    assert db.scalar(select(MetricDaily.id).where(MetricDaily.is_demo.is_(False))) is None
    k = d["kpis"]
    assert abs(k["real_cac"] - k["spend"] / k["confirmed_sales"]) < 1e-6
    assert abs(k["confirmed_roas"] - k["confirmed_revenue"] / k["spend"]) < 1e-6
    assert abs(sum(p["spend"] or 0 for p in d["series"]) - k["spend"]) < 0.01
    camps = admin.get(f"/api/clients/{demo_client['id']}/campaigns?days=30").json()["campaigns"]
    assert len(camps) == 6
    assert abs(sum(c["kpis"]["spend"] for c in camps) - k["spend"]) < 0.01
    assert sum(c["kpis"]["confirmed_sales"] for c in camps) == k["confirmed_sales"]


def test_live_client_without_integration_shows_no_data_and_no_invented_analysis(admin):
    c = admin.post("/api/clients", json={"name": "Cliente Real", "data_mode": "live", "target_cac": "30"}).json()
    d = admin.get(f"/api/clients/{c['id']}/dashboard").json()
    assert d["is_demo"] is False and d["has_data"] is False
    assert d["kpis"]["spend"] is None and d["kpis"]["real_cac"] is None
    assert admin.get(f"/api/clients/{c['id']}/campaigns").json()["campaigns"] == []
    a = analyze(admin, c["id"])
    assert a["recommendations"] == [] and "Não há dados" in a["summary"]["answer"]


# --- análise, aprovação, execução -------------------------------------------------------------------

def test_analysis_produces_one_structured_recommendation_per_campaign(admin, demo_client):
    a = analyze(admin, demo_client["id"])
    recs = by_rule(a)
    assert set(recs) == {"lead_quality", "scale_winner", "creative_fatigue", "tracking_divergence",
                         "insufficient_sample", "keep", "ad_no_results"}
    # Meta Ads Specialist: o anúncio "Imagem combo" gasta sem gerar lead nas 3 campanhas da Meta.
    # Nenhuma recomendação de anúncio para campanhas com amostra insuficiente ou rastreamento duvidoso.
    ad_recs = [r for r in a["recommendations"] if r["rule"] == "ad_no_results"]
    assert len(ad_recs) == 3 and {r["ad_name"] for r in ad_recs} == {"Imagem combo"}
    assert all(r["platform"] == "meta" and r["action_type"] == "pause_ad" for r in ad_recs)
    assert len({r["title"] for r in ad_recs}) == 3  # títulos distinguem a campanha
    assert a["is_demo"] and "DADOS DEMONSTRATIVOS" in a["summary"]["answer"]
    assert recs["lead_quality"]["id"] in a["summary"]["matched_ids"]
    for r in a["recommendations"]:
        assert r["is_demo"] and r["evidence"] and all(e["period"] and e["source"] for e in r["evidence"])
        for field in ("problem", "probable_cause", "hypothesis", "recommended_action", "expected_impact", "risks",
                      "validation_metric", "confidence", "priority"):
            assert r[field], field
    assert recs["keep"]["status"] == recs["insufficient_sample"]["status"] == "informational"
    assert recs["scale_winner"]["status"] == "awaiting_approval"
    assert a["summary"]["finance"]["breakeven_roas"] == 1 / 0.35
    pending = admin.get(f"/api/clients/{demo_client['id']}/recommendations").json()
    assert len(pending) == 7 and pending[0]["priority_score"] >= pending[-1]["priority_score"]


def test_repeated_analysis_does_not_duplicate_pending_recommendations(admin, demo_client):
    first = analyze(admin, demo_client["id"])
    second = analyze(admin, demo_client["id"])
    assert len(admin.get(f"/api/clients/{demo_client['id']}/recommendations").json()) == 7
    assert by_rule(first)["scale_winner"]["id"] == by_rule(second)["scale_winner"]["id"]


def test_approve_executes_simulated_change_with_verification_and_history(admin, demo_client, db):
    cid = demo_client["id"]
    rec = by_rule(analyze(admin, cid))["scale_winner"]
    payload = rec["action_payload"]
    assert payload["from"] == 60.0 and payload["to"] == 72.0
    url = f"/api/clients/{cid}/recommendations/{rec['id']}/decision"
    done = admin.post(url, json={"decision": "approve", "comment": "ok"}).json()
    assert done["status"] == "completed"
    ex = done["executions"][0]
    assert ex["mode"] == "simulated" and ex["verified"] and all(c["passed"] for c in ex["checks"])
    assert ex["before_state"] == {"daily_budget": 60.0} and ex["after_state"] == {"daily_budget": 72.0}
    assert float(db.get(Campaign, payload["campaign_id"]).daily_budget) == 72.0
    # proteção contra operação duplicada
    assert admin.post(url, json={"decision": "approve"}).status_code == 409
    assert float(db.get(Campaign, payload["campaign_id"]).daily_budget) == 72.0
    history = admin.get(f"/api/clients/{cid}/recommendations?scope=history").json()
    assert [h["id"] for h in history] == [rec["id"]] and history[0]["decisions"][0]["comment"] == "ok"
    camp = next(c for c in admin.get(f"/api/clients/{cid}/campaigns").json()["campaigns"]
                if c["id"] == payload["campaign_id"])
    assert camp["daily_budget"] == 72.0 and camp["changes"][0]["verified"] is True
    actions = [e["action"] for e in admin.get(f"/api/audit?client_id={cid}").json()]
    assert actions[:2] == ["execution.completed", "recommendation.approved"]


def test_reject_and_adjustment_change_nothing(admin, demo_client, db):
    cid = demo_client["id"]
    recs = by_rule(analyze(admin, cid))
    scale, fatigue = recs["scale_winner"], recs["creative_fatigue"]
    base = f"/api/clients/{cid}/recommendations"
    assert admin.post(f"{base}/{scale['id']}/decision", json={"decision": "request_adjustment"}).status_code == 422
    adj = admin.post(f"{base}/{scale['id']}/decision",
                     json={"decision": "request_adjustment", "comment": "Subir só 10%"}).json()
    assert adj["status"] == "adjustment_requested" and adj["executions"] == []
    rej = admin.post(f"{base}/{scale['id']}/decision", json={"decision": "reject", "comment": "Sem verba"}).json()
    assert rej["status"] == "rejected" and len(rej["decisions"]) == 2 and rej["executions"] == []
    assert float(db.get(Campaign, scale["action_payload"]["campaign_id"]).daily_budget) == 60.0
    # tarefa manual: aprovação registra a decisão, sem execução automática
    manual = admin.post(f"{base}/{fatigue['id']}/decision", json={"decision": "approve"}).json()
    assert manual["status"] == "approved" and manual["executions"] == []


def test_consultive_level_never_executes(admin, demo_client, db):
    cid = demo_client["id"]
    body = {k: v for k, v in demo_client.items() if k not in ("id", "data_mode", "created_at")}
    assert admin.put(f"/api/clients/{cid}", json={**body, "operation_level": 1}).status_code == 200
    rec = by_rule(analyze(admin, cid))["scale_winner"]
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "approved" and out["executions"] == []
    assert float(db.get(Campaign, rec["action_payload"]["campaign_id"]).daily_budget) == 60.0


def test_safety_blocks_stale_state_and_limit_violation(admin, demo_client, db):
    cid = demo_client["id"]
    rec = by_rule(analyze(admin, cid))["scale_winner"]
    camp = db.get(Campaign, rec["action_payload"]["campaign_id"])
    camp.daily_budget = 65  # orçamento mudou depois da recomendação
    db.commit()
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "failed" and out["executions"][0]["verified"] is False
    assert "Estado atual confere" in [c["check"] for c in out["executions"][0]["checks"] if not c["passed"]]
    db.refresh(camp)
    assert float(camp.daily_budget) == 65.0

    other = admin.post("/api/clients", json={**DEMO_CLIENT, "name": "Outro"}).json()
    rec2 = by_rule(analyze(admin, other["id"]))["scale_winner"]
    row = db.get(Recommendation, rec2["id"])
    row.action_payload = {**row.action_payload, "to": 600.0, "change_pct": 900.0}  # fora do limite de 30%
    db.commit()
    out2 = admin.post(f"/api/clients/{other['id']}/recommendations/{rec2['id']}/decision",
                      json={"decision": "approve"}).json()
    assert out2["status"] == "failed"
    assert "Limite financeiro" in [c["check"] for c in out2["executions"][0]["checks"] if not c["passed"]]


def test_live_client_execution_is_blocked_not_faked(admin, demo_client, db):
    """Sem conector de escrita, uma aprovação em cliente real falha de forma explícita."""
    from app.models import Client
    cid = demo_client["id"]
    rec = by_rule(analyze(admin, cid))["scale_winner"]
    db.get(Client, cid).data_mode = "live"
    db.commit()
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "failed" and out["executions"][0]["mode"] == "live"
    assert float(db.get(Campaign, rec["action_payload"]["campaign_id"]).daily_budget) == 60.0


# --- auditoria --------------------------------------------------------------------------------------

def test_audit_chain_detects_tampering(admin, demo_client, db):
    analyze(admin, demo_client["id"])
    ok = admin.get("/api/audit/verify").json()
    assert ok["valid"] is True and ok["entries"] >= 3
    if db.bind.dialect.name == "postgresql":
        return  # em PostgreSQL a adulteração é barrada pelo gatilho da migração (ver test_migrations)
    victim = db.scalar(select(AuditLog).where(AuditLog.action == "client.created"))
    db.execute(text("UPDATE audit_log SET details = '{\"name\": \"adulterado\"}' WHERE id = :i"), {"i": victim.id})
    db.commit()
    assert audit.verify_chain(db) == {"valid": False, "entries": victim.id - 1, "broken_at_id": victim.id}


def test_user_changes_own_login_and_password(db):
    make_user(db, "admin@borges.local", "admin")
    make_user(db, "outro@example.com", "manager")
    http = login("admin@borges.local")
    url = "/api/auth/me/credentials"
    assert http.put(url, json={"current_password": "errada", "new_password": "nova-senha-1"}).status_code == 403
    assert http.put(url, json={"current_password": "senha-de-teste-123"}).status_code == 422
    assert http.put(url, json={"current_password": "senha-de-teste-123", "new_password": "curta"}).status_code == 422
    assert http.put(url, json={"current_password": "senha-de-teste-123", "new_login": "com espaco"}).status_code == 422
    taken = http.put(url, json={"current_password": "senha-de-teste-123", "new_login": "outro@example.com"})
    assert taken.status_code == 409
    ok = http.put(url, json={"current_password": "senha-de-teste-123", "new_login": "  BorgesOEduardo ",
                             "new_password": "Qwect@1289-teste"})
    assert ok.status_code == 200 and ok.json()["email"] == "borgesoeduardo"
    assert http.get("/api/auth/me").json()["email"] == "borgesoeduardo"  # sessão continua válida
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"email": "admin@borges.local",
                                                "password": "senha-de-teste-123"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": "BorgesOEduardo",
                                                "password": "Qwect@1289-teste"}).status_code == 200
    log = http.get("/api/audit").json()
    change = next(e for e in log if e["action"] == "auth.credentials_changed")
    assert "Qwect" not in str(change) and change["details"]["changes"][0]["to"] == "borgesoeduardo"


def test_clients_work_without_system_timezone_database(admin, monkeypatch):
    """Windows não tem banco de fusos do sistema: o pacote tzdata precisa bastar."""
    import zoneinfo
    monkeypatch.setattr(zoneinfo, "TZPATH", ())
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()
    try:
        created = admin.post("/api/clients", json={"name": "Sem tz do sistema", "data_mode": "live"})
        assert created.status_code == 201, created.text
        assert admin.get("/api/clients").status_code == 200
        assert admin.post("/api/clients", json={"name": "Fuso ruim", "timezone": "Marte/Base"}).status_code == 422
    finally:
        zoneinfo.reset_tzpath()
        zoneinfo.ZoneInfo.clear_cache()


def test_pause_ad_is_simulated_verified_and_not_undone_by_demo_resync(admin, demo_client, db):
    from app.models import Ad
    cid = demo_client["id"]
    rec = next(r for r in analyze(admin, cid)["recommendations"] if r["rule"] == "ad_no_results")
    url = f"/api/clients/{cid}/recommendations/{rec['id']}/decision"
    out = admin.post(url, json={"decision": "approve"}).json()
    ex = out["executions"][0]
    assert out["status"] == "completed" and ex["mode"] == "simulated" and ex["verified"]
    assert ex["before_state"] == {"ad_status": "active"} and ex["after_state"] == {"ad_status": "paused"}
    assert db.get(Ad, rec["ad_id"]).status == "paused"
    assert admin.post(url, json={"decision": "approve"}).status_code == 409
    # regerar os dados demo não "despausa" o anúncio
    assert admin.post(f"/api/clients/{cid}/sync", json={"days": 30}).json()["status"] == "completed"
    db.expire_all()
    assert db.get(Ad, rec["ad_id"]).status == "paused"
    camp = admin.get(f"/api/clients/{cid}/campaigns/{rec['campaign_id']}/breakdown").json()
    paused = [a for s in camp["ad_sets"] for a in s["ads"] if a["id"] == rec["ad_id"]]
    assert paused[0]["status"] == "paused"
    # nova análise: o anúncio já pausado não gera nova recomendação de pausa
    again = analyze(admin, cid)["recommendations"]
    assert not any(r["rule"] == "ad_no_results" and r["ad_id"] == rec["ad_id"] and r["action_type"] == "pause_ad"
                   for r in again)


def test_pause_ad_on_live_client_is_blocked_not_faked(admin, demo_client, db):
    from app.models import Ad, Client
    cid = demo_client["id"]
    rec = next(r for r in analyze(admin, cid)["recommendations"] if r["rule"] == "ad_no_results")
    db.get(Client, cid).data_mode = "live"
    db.commit()
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "failed" and db.get(Ad, rec["ad_id"]).status == "active"
