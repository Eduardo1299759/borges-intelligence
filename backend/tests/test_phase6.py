"""Fase 6: rotinas, worker, alertas, relatórios e memória de aprendizados."""
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import worker
from app.automation import routines
from app.models import (
    Alert,
    Execution,
    Learning,
    Recommendation,
    Report,
    Routine,
    RoutineRun,
    User,
    UserClientAccess,
)
from tests.conftest import login, make_user
from tests.test_growth import campaign_ads, new_experiment


def routine_id(admin, cid, kind):
    return next(r["id"] for r in admin.get(f"/api/clients/{cid}/routines").json()["routines"] if r["kind"] == kind)


def test_default_routines_and_schedule_edit(admin, demo_client, db):
    cid = demo_client["id"]
    data = admin.get(f"/api/clients/{cid}/routines").json()
    assert data["timezone"] == demo_client["timezone"]
    kinds = [r["kind"] for r in data["routines"]]
    assert kinds == ["daily_audit", "competitive_review", "weekly_report", "monthly_report", "creative_review"]
    assert all(r["enabled"] and r["next_run_at"] for r in data["routines"])
    assert len(admin.get(f"/api/clients/{cid}/routines").json()["routines"]) == 5  # idempotente
    rid = routine_id(admin, cid, "weekly_report")
    r = admin.patch(f"/api/clients/{cid}/routines/{rid}", json={"time": "07:30", "weekday": 4})
    assert r.status_code == 200 and r.json()["time"] == "07:30" and r.json()["weekday"] == 4
    assert admin.patch(f"/api/clients/{cid}/routines/{rid}", json={"time": "25:00"}).status_code == 422
    assert admin.patch(f"/api/clients/{cid}/routines/{rid}", json={"interval_days": 2}).status_code == 422
    assert admin.patch(f"/api/clients/{cid}/routines/{rid}", json={"enabled": False}).json()["enabled"] is False
    make_user(db, "viewer@example.com", "viewer")
    viewer = db.scalar(select(User).where(User.email == "viewer@example.com"))
    db.add(UserClientAccess(user_id=viewer.id, client_id=cid))
    db.commit()
    v = login("viewer@example.com")
    assert v.get(f"/api/clients/{cid}/routines").status_code == 200
    assert v.patch(f"/api/clients/{cid}/routines/{rid}", json={"enabled": True}).status_code == 403
    assert v.post(f"/api/clients/{cid}/routines/{rid}/run").status_code == 403


def test_daily_audit_creates_analysis_report_and_dedupes_alerts(admin, demo_client, db):
    cid = demo_client["id"]
    rid = routine_id(admin, cid, "daily_audit")
    run = admin.post(f"/api/clients/{cid}/routines/{rid}/run").json()
    assert run["status"] == "completed", run
    s = run["summary"]
    assert s["analysis_id"] and s["report_id"] and "sync" not in s  # demo não sincroniza
    rep = admin.get(f"/api/clients/{cid}/reports/{s['report_id']}").json()
    assert rep["kind"] == "daily" and rep["is_demo"] and rep["content"]["executive_summary"]
    alerts_before = db.scalars(select(Alert).where(Alert.client_id == cid)).all()
    again = admin.post(f"/api/clients/{cid}/routines/{rid}/run").json()
    assert again["status"] == "completed" and again["summary"]["alerts"] == []  # sem alerta repetido
    assert len(db.scalars(select(Alert).where(Alert.client_id == cid)).all()) == len(alerts_before)
    runs = admin.get(f"/api/clients/{cid}/routine-runs").json()
    assert len(runs) == 2 and runs[0]["label"] == "Auditoria diária"
    actions = [a["action"] for a in admin.get(f"/api/audit?client_id={cid}").json()]
    assert actions.count("routine.completed") == 2
    # nenhuma rotina executa mudanças: só recomendações aguardando aprovação
    assert db.scalar(select(Execution.id).where(Execution.client_id == cid)) is None


def test_worker_runs_due_routines_once_and_advances_schedule(admin, demo_client, db, session_factory):
    cid = demo_client["id"]
    admin.get(f"/api/clients/{cid}/routines")
    past = datetime.now(UTC) - timedelta(minutes=5)
    for r in db.scalars(select(Routine).where(Routine.client_id == cid)):
        r.next_run_at = past if r.kind in ("weekly_report", "competitive_review") else past + timedelta(days=30)
    db.commit()
    assert worker.cycle() == 2
    db.expire_all()
    runs = db.scalars(select(RoutineRun).where(RoutineRun.client_id == cid)).all()
    assert sorted(r.status for r in runs) == ["completed", "completed"]
    comp = next(r for r in runs if r.summary.get("skipped"))
    assert "concorrente" in comp.summary["skipped"]
    for r in db.scalars(select(Routine).where(Routine.client_id == cid, Routine.kind == "weekly_report")):
        assert r.next_run_at.replace(tzinfo=UTC) > datetime.now(UTC) and r.last_run_at is not None
    assert worker.cycle() == 0  # não roda de novo
    assert db.scalars(select(Report).where(Report.client_id == cid, Report.kind == "weekly")).first()


def test_inactive_clients_and_disabled_routines_do_not_run(admin, demo_client, db):
    cid = demo_client["id"]
    admin.get(f"/api/clients/{cid}/routines")
    for r in db.scalars(select(Routine).where(Routine.client_id == cid)):
        r.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        r.enabled = r.kind != "weekly_report"
    db.commit()
    from app.models import Client
    client = db.get(Client, cid)
    client.is_active = False
    db.commit()
    assert routines.claim_due(db, datetime.now(UTC)) == []
    client.is_active = True
    db.commit()
    claimed = routines.claim_due(db, datetime.now(UTC))
    assert len(claimed) == 4 and routines.claim_due(db, datetime.now(UTC)) == []


def test_failure_is_recorded_and_stale_runs_are_closed(admin, demo_client, db, monkeypatch):
    cid = demo_client["id"]
    rid = routine_id(admin, cid, "monthly_report")

    def boom(*_a):
        raise RuntimeError("falha simulada")
    monkeypatch.setitem(routines.HANDLERS, "monthly_report", boom)
    run = admin.post(f"/api/clients/{cid}/routines/{rid}/run").json()
    assert run["status"] == "failed" and "falha simulada" in run["error"]
    assert "routine.failed" in [a["action"] for a in admin.get(f"/api/audit?client_id={cid}").json()]
    stale = RoutineRun(routine_id=rid, client_id=cid, status="running", triggered_by="Agendador",
                       started_at=datetime.now(UTC) - timedelta(hours=3))
    db.add(stale)
    db.commit()
    assert routines.fail_stale_runs(db, datetime.now(UTC)) == 1
    db.refresh(stale)
    assert stale.status == "failed" and stale.finished_at


def test_reports_weekly_and_monthly(admin, demo_client, db):
    cid = demo_client["id"]
    w = admin.post(f"/api/clients/{cid}/reports", json={"kind": "weekly"})
    assert w.status_code == 201
    c = w.json()["content"]
    start, end = date.fromisoformat(c["period"]["start"]), date.fromisoformat(c["period"]["end"])
    assert (end - start).days == 6 and date.fromisoformat(c["compare"]["end"]) == start - timedelta(days=1)
    keys = {k["key"] for k in c["kpis"]}
    assert {"spend", "real_cac", "confirmed_roas", "leads"} <= keys
    spend = next(k for k in c["kpis"] if k["key"] == "spend")
    assert spend["current"] > 0 and spend["previous"] > 0 and spend["change"] is not None
    assert c["campaigns"] and c["sources"] and c["notes"] and c["is_demo"]
    m = admin.post(f"/api/clients/{cid}/reports", json={"kind": "monthly"}).json()["content"]
    ms, me = date.fromisoformat(m["period"]["start"]), date.fromisoformat(m["period"]["end"])
    assert ms.day == 1 and (me + timedelta(days=1)).day == 1  # mês completo
    assert admin.post(f"/api/clients/{cid}/reports", json={"kind": "yearly"}).status_code == 422
    assert len(admin.get(f"/api/clients/{cid}/reports").json()) == 2
    make_user(db, "x@example.com", "manager")
    other = login("x@example.com")
    rep_id = admin.get(f"/api/clients/{cid}/reports").json()[0]["id"]
    assert other.get(f"/api/clients/{cid}/reports/{rep_id}").status_code == 404


def test_experiment_conclusion_becomes_learning_and_validation_rules(admin, demo_client, db):
    cid = demo_client["id"]
    ads = campaign_ads(db, cid, "Conversas WhatsApp — Público aberto")
    e = new_experiment(admin, cid, ads)
    base = f"/api/clients/{cid}/experiments/{e['id']}"
    admin.post(f"{base}/start", json={"start_date": (date.today() - timedelta(days=15)).isoformat()})
    done = admin.post(f"{base}/conclude", json={"outcome": "success",
                                                "learning": "Depoimento em vídeo converte melhor neste público."})
    verdict = done.json()["evaluation"]["verdict"]["status"]
    lr = admin.get(f"/api/clients/{cid}/learnings").json()
    assert len(lr) == 1 and lr[0]["source_type"] == "experiment"
    assert lr[0]["status"] == ("validated" if verdict == "significant_better" else "hypothesis")
    manual = admin.post(f"/api/clients/{cid}/learnings", json={
        "title": "Horário noturno", "statement": "Leads da noite parecem responder melhor no WhatsApp."}).json()
    assert manual["status"] == "hypothesis" and manual["reliability"] == "baixa"
    found = admin.get(f"/api/clients/{cid}/learnings?q=whatsapp noite").json()
    assert [x["id"] for x in found] == [manual["id"]]
    assert admin.get(f"/api/clients/{cid}/learnings?q=inexistentexyz").json() == []
    r = admin.post(f"/api/clients/{cid}/learnings/{manual['id']}/validate", json={"experiment_id": e["id"]})
    if verdict in ("significant_better", "significant_worse"):
        assert r.status_code == 200 and r.json()["status"] == "validated"
    else:
        assert r.status_code == 409
    other = new_experiment(admin, cid, ads, name="Outro")
    assert admin.post(f"/api/clients/{cid}/learnings/{manual['id']}/validate",
                      json={"experiment_id": other["id"]}).status_code == 409  # rascunho não valida
    ref = admin.post(f"/api/clients/{cid}/learnings/{manual['id']}/refute", json={"reason": "Dados do CRM contrariam"})
    assert ref.json()["status"] == "refuted" and ref.json()["evidence"]["refuted_reason"]


def test_execution_impact_becomes_low_reliability_hypothesis(admin, demo_client, db):
    cid = demo_client["id"]
    rid = routine_id(admin, cid, "daily_audit")
    admin.post(f"/api/clients/{cid}/routines/{rid}/run")
    rec = db.scalar(select(Recommendation).where(Recommendation.client_id == cid,
                                                 Recommendation.campaign_id.is_not(None)))
    finished = datetime.now(UTC) - timedelta(days=12)
    db.add(Execution(recommendation_id=rec.id, client_id=cid, idempotency_key=f"t-{rec.id}", mode="simulated",
                     status="completed", checks=[], started_at=finished, finished_at=finished))
    db.commit()
    imp = admin.get(f"/api/clients/{cid}/impact").json()
    assert len(imp) == 1 and imp[0]["metric"] in ("cpl", "real_cac") and imp[0]["before"]["spend"] > 0
    admin.post(f"/api/clients/{cid}/routines/{rid}/run")
    lr = db.scalars(select(Learning).where(Learning.client_id == cid, Learning.source_type == "execution_impact")).all()
    assert len(lr) == 1 and lr[0].status == "hypothesis" and lr[0].reliability == "baixa"
    assert "não prova causa" in lr[0].statement
    admin.post(f"/api/clients/{cid}/routines/{rid}/run")  # não duplica
    assert len(db.scalars(select(Learning).where(Learning.source_type == "execution_impact")).all()) == 1


def test_creative_review_and_alert_status(admin, demo_client, db):
    cid = demo_client["id"]
    run = admin.post(f"/api/clients/{cid}/routines/{routine_id(admin, cid, 'creative_review')}/run").json()
    assert run["status"] == "completed" and run["summary"]["flagged"]  # campanha com fadiga no demo
    alerts = admin.get(f"/api/clients/{cid}/alerts").json()
    fatigue = [a for a in alerts if a["kind"] == "creative_fatigue"]
    assert fatigue and all(a["is_demo"] for a in fatigue)
    aid = fatigue[0]["id"]
    assert admin.post(f"/api/clients/{cid}/alerts/{aid}/status", json={"status": "resolved"}).json()["status"] == \
        "resolved"
    assert aid not in [a["id"] for a in admin.get(f"/api/clients/{cid}/alerts").json()]
    assert aid in [a["id"] for a in admin.get(f"/api/clients/{cid}/alerts?status=resolved").json()]
    assert admin.post(f"/api/clients/{cid}/alerts/{aid}/status", json={"status": "open"}).status_code == 422


@pytest.mark.parametrize("path", ["routines", "routine-runs", "alerts", "reports", "learnings", "impact"])
def test_phase6_endpoints_are_isolated(admin, demo_client, db, path):
    make_user(db, "x@example.com", "manager")
    assert login("x@example.com").get(f"/api/clients/{demo_client['id']}/{path}").status_code == 404
