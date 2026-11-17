"""Agente 12 — Operations & Safety: rotinas automáticas por cliente.

As rotinas só leem dados, analisam, geram relatórios, alertas e aprendizados. Nenhuma rotina altera campanhas:
recomendações continuam esperando aprovação humana na central de aprovações.
"""
from __future__ import annotations

import calendar
import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import core
from app.api.routes.insights import resolve_period
from app.automation import anomalies
from app.automation.schedule import DEFAULTS, LABELS, Schedule, next_run
from app.competitive import service as competitive
from app.creative.library import library
from app.experiments import service as experiments
from app.learning import impact
from app.learning import service as learnings
from app.models import (
    REC_INFO,
    Alert,
    Campaign,
    Client,
    Competitor,
    Experiment,
    MetricDaily,
    Recommendation,
    Report,
    Routine,
    RoutineRun,
)
from app.reports import builder
from app.services import audit
from app.services import sync as sync_service

log = logging.getLogger("borges.routines")
STALE_AFTER = timedelta(hours=2)
READY = {"significant_better", "significant_worse", "no_difference"}


def schedule_of(r: Routine) -> Schedule:
    return Schedule(r.schedule_type, r.time, r.weekday, r.day_of_month, r.interval_days)


def ensure_defaults(db: Session, client: Client) -> list[Routine]:
    existing = {r.kind: r for r in db.scalars(select(Routine).where(Routine.client_id == client.id))}
    now = datetime.now(UTC)
    for kind, spec in DEFAULTS.items():
        s = Schedule(*spec)
        if kind not in existing:
            r = Routine(client_id=client.id, kind=kind, enabled=True, schedule_type=s.type, time=s.time,
                        weekday=s.weekday, day_of_month=s.day_of_month, interval_days=s.interval_days,
                        next_run_at=next_run(s, client.timezone, now))
            db.add(r)
            existing[kind] = r
    db.flush()
    return [existing[k] for k in DEFAULTS]


# --- Alertas -----------------------------------------------------------------------------------------

def raise_alert(db: Session, client: Client, kind: str, severity: str, title: str, detail: str,
                evidence: dict[str, Any], campaign_id: int | None = None) -> Alert | None:
    """Cria o alerta se não houver outro aberto do mesmo tipo para a mesma campanha (sem repetição diária)."""
    q = select(Alert.id).where(Alert.client_id == client.id, Alert.kind == kind, Alert.status == "open")
    q = q.where(Alert.campaign_id.is_(None) if campaign_id is None else Alert.campaign_id == campaign_id)
    if kind == "experiment_ready":
        q = q.where(Alert.title == title)
    if db.scalar(q):
        return None
    alert = Alert(client_id=client.id, campaign_id=campaign_id, kind=kind, severity=severity, title=title,
                  detail=detail, evidence=evidence, is_demo=client.data_mode == "demo")
    db.add(alert)
    db.flush()
    return alert


def detect_anomalies(db: Session, client: Client, last_day: date) -> list[Alert]:
    start = last_day - timedelta(days=21)
    rows = db.execute(select(MetricDaily.campaign_id, MetricDaily.date, MetricDaily.spend, MetricDaily.leads)
                      .where(MetricDaily.client_id == client.id, MetricDaily.date >= start,
                             MetricDaily.date <= last_day)).all()
    per: dict[int, dict[date, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for cid, d, spend, leads in rows:
        per[cid][d][0] += float(spend or 0)
        per[cid][d][1] += float(leads or 0)
    names = {c.id: c.name for c in db.scalars(select(Campaign).where(Campaign.client_id == client.id))}
    created: list[Alert] = []
    for cid, days in per.items():
        series = [anomalies.Day(start + timedelta(days=i), *days.get(start + timedelta(days=i), [0.0, 0.0]))
                  for i in range(22)]
        for f in anomalies.campaign_anomalies(names.get(cid, str(cid)), series):
            a = raise_alert(db, client, f.kind, f.severity, f.title, f.detail, f.evidence, cid)
            if a:
                created.append(a)
    if client.monthly_budget:
        month_start = last_day.replace(day=1)
        mtd = sum(float(s or 0) for (s,) in db.execute(
            select(MetricDaily.spend).where(MetricDaily.client_id == client.id, MetricDaily.date >= month_start,
                                            MetricDaily.date <= last_day)))
        f = anomalies.pacing_anomaly(mtd, float(client.monthly_budget), last_day.day,
                                     calendar.monthrange(last_day.year, last_day.month)[1])
        if f:
            a = raise_alert(db, client, f.kind, f.severity, f.title, f.detail, f.evidence)
            if a:
                created.append(a)
    return created


# --- Rotinas -----------------------------------------------------------------------------------------

def _save_report(db: Session, client: Client, kind: str, content: dict[str, Any], actor: str) -> Report:
    content = json.loads(json.dumps(content, default=str))
    rep = Report(client_id=client.id, kind=kind, period_start=date.fromisoformat(content["period"]["start"]),
                 period_end=date.fromisoformat(content["period"]["end"]), content=content,
                 is_demo=client.data_mode == "demo", created_by=actor)
    db.add(rep)
    db.flush()
    return rep


def generate_report(db: Session, client: Client, kind: str, actor: str) -> Report:
    _, last = resolve_period(db, client, 1)
    return _save_report(db, client, kind, builder.build(db, client, kind, last), actor)


def _daily_audit(db: Session, client: Client, actor: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if client.data_mode == "live":
        try:
            run = sync_service.run_sync(db, client, None, 3, actor_label=actor)
            out["sync"] = {"status": run.status, "stats": run.stats, "error": run.error}
        except sync_service.SyncUnavailable as exc:
            out["sync"] = {"status": "skipped", "reason": str(exc)}
    start, last = resolve_period(db, client, 7)
    analysis = core.analyze(db, client, None, "Auditoria diária automática", start, last)
    out["analysis_id"] = analysis.id
    out["new_recommendations"] = len(db.scalars(select(Recommendation.id).where(
        Recommendation.analysis_run_id == analysis.id, Recommendation.status != REC_INFO)).all())
    out["alerts"] = [a.title for a in detect_anomalies(db, client, last)]
    for e in db.scalars(select(Experiment).where(Experiment.client_id == client.id, Experiment.status == "running")):
        ev = experiments.evaluation(db, client, e)
        status = (ev or {}).get("verdict", {}).get("status")
        if status in READY:
            a = raise_alert(db, client, "experiment_ready", "media", f"Experimento pronto para conclusão: {e.name}",
                            f"Resultado: {ev['verdict']['label']}. Conclua o experimento para registrar o "
                            "aprendizado.", {"experiment_id": e.id, "verdict": status}, e.campaign_id)
            if a:
                out["alerts"].append(a.title)
    new_learnings = []
    for ex in impact.pending_executions(db, client):
        m = impact.measure(db, client, ex, last)
        if m:
            lr = learnings.from_impact(db, client, m)
            if lr:
                new_learnings.append(lr.title)
    out["learnings"] = new_learnings
    out["report_id"] = generate_report(db, client, "daily", actor).id
    return out


def _competitive(db: Session, client: Client, actor: str) -> dict[str, Any]:
    if not db.scalar(select(Competitor.id).where(Competitor.client_id == client.id)):
        return {"skipped": "Nenhum concorrente cadastrado no Radar."}
    data = competitive.insights(db, client)
    today = datetime.now(UTC).date()
    content = {"kind": "competitive", "label": "Revisão competitiva", "client": client.name,
               "is_demo": client.data_mode == "demo", "period": {"start": str(today), "end": str(today)},
               "insights": data,
               "notes": ["Baseado apenas nos anúncios de concorrentes cadastrados manualmente no Radar."]}
    return {"report_id": _save_report(db, client, "competitive", content, actor).id, "source": data.get("source")}


def _creative(db: Session, client: Client, actor: str) -> dict[str, Any]:
    start, last = resolve_period(db, client, 30)
    flagged = []
    for ad in library(db, client, start, last):
        share = ad["spend_share_in_campaign"] or 0
        if share < 0.2 or (ad["status"] or "active").lower() not in ("active", "enabled"):
            continue
        if ad["trend"] == "ctr_caindo" or ad["class"] in ("fraco", "sem_resultado"):
            reason = ("teve queda de ao menos 20% no CTR entre a 1ª e a 2ª metade do período"
                      if ad["trend"] == "ctr_caindo" else f"foi classificado como “{ad['class_label']}”")
            a = raise_alert(db, client, "creative_fatigue", "media", f"Criativo para revisar: {ad['name']}",
                            f"Recebe {share * 100:.0f}% da verba da campanha “{ad['campaign']}” e {reason} "
                            f"({start:%d/%m/%Y} a {last:%d/%m/%Y}). Sugestão: criar um briefing de novas variações "
                            "em Creative Studio.",
                            {"ad_id": ad["ad_id"], "trend": ad["trend"], "class": ad["class"],
                             "spend_share": share, "ctr_first_half": ad["ctr_first_half"],
                             "ctr_second_half": ad["ctr_second_half"]}, ad["campaign_id"])
            if a:
                flagged.append(ad["name"])
    return {"flagged": flagged, "period": f"{start:%d/%m/%Y} a {last:%d/%m/%Y}"}


HANDLERS = {
    "daily_audit": _daily_audit,
    "competitive_review": _competitive,
    "weekly_report": lambda db, c, actor: {"report_id": generate_report(db, c, "weekly", actor).id},
    "monthly_report": lambda db, c, actor: {"report_id": generate_report(db, c, "monthly", actor).id},
    "creative_review": _creative,
}


def execute(db: Session, routine: Routine, triggered_by: str) -> RoutineRun:
    """Roda a rotina e registra o resultado. Uma falha é registrada e não interrompe as outras rotinas."""
    client = db.get(Client, routine.client_id)
    run = RoutineRun(routine_id=routine.id, client_id=client.id, status="running", triggered_by=triggered_by)
    db.add(run)
    db.commit()
    actor = f"Rotina: {LABELS[routine.kind]}"
    try:
        summary = HANDLERS[routine.kind](db, client, actor)
        run.status, run.summary = "completed", summary
    except Exception as exc:  # noqa: BLE001 — o erro fica registrado na execução e na auditoria
        db.rollback()
        log.exception("Rotina %s do cliente %s falhou", routine.kind, client.id)
        run = db.get(RoutineRun, run.id)
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
    run.finished_at = datetime.now(UTC)
    routine = db.get(Routine, routine.id)
    routine.last_run_at = run.started_at
    audit.record(db, action=f"routine.{run.status}", actor=None, actor_label=triggered_by, client_id=client.id,
                 entity_type="routine_run", entity_id=run.id,
                 details={"kind": routine.kind, "error": run.error, "summary": run.summary})
    db.commit()
    return run


def claim_due(db: Session, now: datetime, limit: int = 20) -> list[int]:
    """Reserva rotinas vencidas avançando o próximo horário na mesma transação.

    No PostgreSQL usa FOR UPDATE SKIP LOCKED: dois workers nunca pegam a mesma rotina.
    """
    q = (select(Routine).join(Client, Client.id == Routine.client_id)
         .where(Routine.enabled.is_(True), Client.is_active.is_(True), Routine.next_run_at <= now)
         .order_by(Routine.next_run_at).limit(limit))
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True, of=Routine)
    rows = db.scalars(q).all()
    for r in rows:
        tz = db.get(Client, r.client_id).timezone
        r.next_run_at = next_run(schedule_of(r), tz, now, last_run=now)
    db.commit()
    return [r.id for r in rows]


def fail_stale_runs(db: Session, now: datetime) -> int:
    stale = db.scalars(select(RoutineRun).where(RoutineRun.status == "running",
                                                RoutineRun.started_at < now - STALE_AFTER)).all()
    for r in stale:
        r.status, r.error, r.finished_at = "failed", "Interrompida (o processo parou antes de terminar).", now
    db.commit()
    return len(stale)


def tick(db: Session, now: datetime | None = None) -> list[RoutineRun]:
    now = now or datetime.now(UTC)
    fail_stale_runs(db, now)
    for client in db.scalars(select(Client).where(Client.is_active.is_(True))).all():
        ensure_defaults(db, client)
    db.commit()
    return [execute(db, db.get(Routine, rid), "Agendador") for rid in claim_due(db, now)]
