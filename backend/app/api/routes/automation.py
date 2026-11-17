"""Fase 6: rotinas automáticas, alertas, relatórios e memória de aprendizados."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes.insights import resolve_period
from app.automation import routines as routine_service
from app.automation.schedule import LABELS, next_run
from app.core.db import get_db
from app.learning import impact
from app.learning import service as learnings
from app.models import Alert, Experiment, Learning, Report, Routine, RoutineRun, User
from app.services import audit
from app.services.access import get_client_or_404, require_role

router = APIRouter(prefix="/clients/{client_id}", tags=["automation"])
EDITORS = ("admin", "manager", "analyst")
MANAGERS = ("admin", "manager")


def _routine_out(r: Routine, last: RoutineRun | None) -> dict:
    return {"id": r.id, "kind": r.kind, "label": LABELS[r.kind], "enabled": r.enabled,
            "schedule_type": r.schedule_type, "time": r.time, "weekday": r.weekday, "day_of_month": r.day_of_month,
            "interval_days": r.interval_days, "next_run_at": r.next_run_at, "last_run_at": r.last_run_at,
            "last_status": last.status if last else None, "last_error": last.error if last else None}


def _run_out(r: RoutineRun, kind: str | None = None) -> dict:
    return {"id": r.id, "routine_id": r.routine_id, "kind": kind, "label": LABELS.get(kind or "", kind),
            "status": r.status, "triggered_by": r.triggered_by, "summary": r.summary, "error": r.error,
            "started_at": r.started_at, "finished_at": r.finished_at}


def _get(db: Session, model, obj_id: int, client_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.client_id != client_id:
        raise HTTPException(404, f"{label} não encontrado.")
    return obj


# --- Rotinas ---------------------------------------------------------------------------------------

@router.get("/routines")
def list_routines(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    items = routine_service.ensure_defaults(db, client)
    db.commit()
    out = []
    for r in items:
        last = db.scalar(select(RoutineRun).where(RoutineRun.routine_id == r.id).order_by(RoutineRun.id.desc()))
        out.append(_routine_out(r, last))
    return {"timezone": client.timezone, "routines": out}


class RoutineUpdate(BaseModel):
    enabled: bool | None = None
    time: str | None = None
    weekday: int | None = Field(None, ge=0, le=6)
    day_of_month: int | None = Field(None, ge=1, le=31)
    interval_days: int | None = Field(None, ge=1, le=30)

    @field_validator("time")
    @classmethod
    def _time(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("Use o formato HH:MM (ex.: 08:00).")
        return v


@router.patch("/routines/{routine_id}")
def update_routine(client_id: int, routine_id: int, body: RoutineUpdate, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_role(user, *MANAGERS)
    client = get_client_or_404(db, user, client_id)
    r = _get(db, Routine, routine_id, client.id, "Rotina")
    changes = body.model_dump(exclude_unset=True)
    allowed = {"enabled", "time"} | {"weekly": {"weekday"}, "monthly": {"day_of_month"},
                                     "every_n_days": {"interval_days"}}.get(r.schedule_type, set())
    if bad := set(changes) - allowed:
        raise HTTPException(422, f"Campos não se aplicam a esta rotina: {', '.join(sorted(bad))}.")
    for k, v in changes.items():
        if v is None:
            raise HTTPException(422, f"{k} não pode ficar vazio.")
        setattr(r, k, v)
    r.next_run_at = next_run(routine_service.schedule_of(r), client.timezone, datetime.now(UTC), r.last_run_at)
    audit.record(db, action="routine.updated", actor=user, client_id=client.id, entity_type="routine",
                 entity_id=r.id, details={"kind": r.kind, **changes})
    db.commit()
    return _routine_out(r, None)


@router.post("/routines/{routine_id}/run")
def run_routine(client_id: int, routine_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    r = _get(db, Routine, routine_id, client.id, "Rotina")
    if db.scalar(select(RoutineRun.id).where(RoutineRun.routine_id == r.id, RoutineRun.status == "running")):
        raise HTTPException(409, "Esta rotina já está em execução.")
    run = routine_service.execute(db, r, f"Manual: {user.email}")
    return _run_out(run, r.kind)


@router.get("/routine-runs")
def list_runs(client_id: int, limit: int = Query(30, ge=1, le=200), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rows = db.execute(select(RoutineRun, Routine.kind).join(Routine, Routine.id == RoutineRun.routine_id)
                      .where(RoutineRun.client_id == client.id).order_by(RoutineRun.id.desc()).limit(limit)).all()
    return [_run_out(r, kind) for r, kind in rows]


# --- Alertas ---------------------------------------------------------------------------------------

@router.get("/alerts")
def list_alerts(client_id: int, status: Literal["open", "acknowledged", "resolved", "all"] = "open",
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    q = select(Alert).where(Alert.client_id == client.id).order_by(Alert.id.desc()).limit(100)
    if status != "all":
        q = q.where(Alert.status == status)
    order = {"alta": 0, "media": 1, "baixa": 2}
    rows = sorted(db.scalars(q), key=lambda a: (order.get(a.severity, 3), -a.id))
    return [{"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "detail": a.detail,
             "evidence": a.evidence, "status": a.status, "is_demo": a.is_demo, "campaign_id": a.campaign_id,
             "created_at": a.created_at} for a in rows]


class AlertStatus(BaseModel):
    status: Literal["acknowledged", "resolved"]


@router.post("/alerts/{alert_id}/status")
def set_alert_status(client_id: int, alert_id: int, body: AlertStatus, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    a = _get(db, Alert, alert_id, client.id, "Alerta")
    a.status, a.updated_at = body.status, datetime.now(UTC)
    audit.record(db, action=f"alert.{body.status}", actor=user, client_id=client.id, entity_type="alert",
                 entity_id=a.id, details={"title": a.title})
    db.commit()
    return {"id": a.id, "status": a.status}


# --- Relatórios ------------------------------------------------------------------------------------

def _report_meta(r: Report) -> dict:
    return {"id": r.id, "kind": r.kind, "label": r.content.get("label"), "period_start": r.period_start,
            "period_end": r.period_end, "is_demo": r.is_demo, "created_by": r.created_by, "created_at": r.created_at}


@router.get("/reports")
def list_reports(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rows = db.scalars(select(Report).where(Report.client_id == client.id).order_by(Report.id.desc()).limit(100))
    return [_report_meta(r) for r in rows]


class ReportIn(BaseModel):
    kind: Literal["daily", "weekly", "monthly"]


@router.post("/reports", status_code=201)
def create_report(client_id: int, body: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    rep = routine_service.generate_report(db, client, body.kind, user.email)
    audit.record(db, action="report.generated", actor=user, client_id=client.id, entity_type="report",
                 entity_id=rep.id, details={"kind": body.kind, "period": [str(rep.period_start), str(rep.period_end)]})
    db.commit()
    return {**_report_meta(rep), "content": rep.content}


@router.get("/reports/{report_id}")
def get_report(client_id: int, report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rep = _get(db, Report, report_id, client.id, "Relatório")
    return {**_report_meta(rep), "content": rep.content}


# --- Aprendizados ----------------------------------------------------------------------------------

def _learning_out(lr: Learning) -> dict:
    return {"id": lr.id, "title": lr.title, "statement": lr.statement, "context": lr.context,
            "source_type": lr.source_type, "source_ref": lr.source_ref, "evidence": lr.evidence, "status": lr.status,
            "reliability": lr.reliability, "created_by": lr.created_by, "created_at": lr.created_at,
            "validated_at": lr.validated_at}


@router.get("/learnings")
def list_learnings(client_id: int, q: str | None = Query(None, max_length=200),
                   status: Literal["hypothesis", "validated", "refuted"] | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    return [_learning_out(lr) for lr in learnings.search(db, client, q, status)]


class LearningIn(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    statement: str = Field(min_length=10, max_length=4000)
    context: str | None = Field(None, max_length=2000)


@router.post("/learnings", status_code=201)
def create_learning(client_id: int, body: LearningIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    lr = Learning(client_id=client.id, title=body.title.strip(), statement=body.statement.strip(),
                  context=body.context, source_type="manual", evidence={}, status="hypothesis",
                  reliability="baixa", created_by=user.email)
    db.add(lr)
    db.flush()
    audit.record(db, action="learning.created", actor=user, client_id=client.id, entity_type="learning",
                 entity_id=lr.id, details={"title": lr.title})
    db.commit()
    return _learning_out(lr)


class ValidateIn(BaseModel):
    experiment_id: int


@router.post("/learnings/{learning_id}/validate")
def validate_learning(client_id: int, learning_id: int, body: ValidateIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_role(user, *MANAGERS)
    client = get_client_or_404(db, user, client_id)
    lr = _get(db, Learning, learning_id, client.id, "Aprendizado")
    exp = _get(db, Experiment, body.experiment_id, client.id, "Experimento")
    try:
        learnings.validate_with_experiment(db, lr, exp)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit.record(db, action="learning.validated", actor=user, client_id=client.id, entity_type="learning",
                 entity_id=lr.id, details={"experiment_id": exp.id})
    db.commit()
    return _learning_out(lr)


class RefuteIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@router.post("/learnings/{learning_id}/refute")
def refute_learning(client_id: int, learning_id: int, body: RefuteIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    require_role(user, *MANAGERS)
    client = get_client_or_404(db, user, client_id)
    lr = _get(db, Learning, learning_id, client.id, "Aprendizado")
    lr.status = "refuted"
    lr.evidence = {**(lr.evidence or {}), "refuted_reason": body.reason, "refuted_by": user.email,
                   "refuted_at": datetime.now(UTC).isoformat()}
    audit.record(db, action="learning.refuted", actor=user, client_id=client.id, entity_type="learning",
                 entity_id=lr.id, details={"reason": body.reason})
    db.commit()
    return _learning_out(lr)


@router.get("/impact")
def impact_list(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Antes x depois de cada execução concluída (7 dias). Hipótese, não prova de causa."""
    client = get_client_or_404(db, user, client_id)
    _, last = resolve_period(db, client, 1)
    out = []
    for ex in impact.pending_executions(db, client):
        m = impact.measure(db, client, ex, last)
        out.append(m or {"execution_id": ex.id, "pending": True,
                         "note": "Aguardando 7 dias completos de dados após a mudança."})
    return out
