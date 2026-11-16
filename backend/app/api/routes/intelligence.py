"""Central de inteligência (análises) e Central de aprovação (decisões)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import core
from app.api.deps import current_user
from app.api.routes.insights import resolve_period
from app.api.serializers import recommendation_out
from app.core.db import get_db
from app.execution import executor
from app.models import REC_ADJUST, REC_AWAITING, REC_INFO, AnalysisRun, Recommendation, User
from app.schemas import AnalysisIn, AnalysisOut, DecisionIn, RecommendationOut
from app.services.access import get_client_or_404, require_role

router = APIRouter(prefix="/clients/{client_id}", tags=["intelligence"])


def _analysis_out(db: Session, run: AnalysisRun) -> AnalysisOut:
    ids = (run.summary or {}).get("recommendation_ids", [])
    recs = {r.id: r for r in db.scalars(select(Recommendation).where(Recommendation.id.in_(ids)))}
    return AnalysisOut(id=run.id, question=run.question, period_start=run.period_start, period_end=run.period_end,
                       status=run.status, is_demo=run.is_demo, summary=run.summary, created_at=run.created_at,
                       recommendations=[recommendation_out(recs[i]) for i in ids if i in recs])


@router.post("/analyses", response_model=AnalysisOut, status_code=201)
def create_analysis(client_id: int, body: AnalysisIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    require_role(user, "admin", "manager", "analyst")
    client = get_client_or_404(db, user, client_id)
    start, end = resolve_period(db, client, body.days)
    run = core.analyze(db, client, user, body.question.strip(), start, end)
    db.commit()
    return _analysis_out(db, run)


@router.get("/analyses", response_model=list[AnalysisOut])
def list_analyses(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    runs = db.scalars(select(AnalysisRun).where(AnalysisRun.client_id == client.id)
                      .order_by(AnalysisRun.id.desc()).limit(10)).all()
    return [_analysis_out(db, r) for r in runs]


@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(client_id: int, scope: Literal["pending", "history"] = "pending",
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    q = select(Recommendation).where(Recommendation.client_id == client.id)
    if scope == "pending":
        q = q.where(Recommendation.status.in_([REC_AWAITING, REC_ADJUST])).order_by(
            Recommendation.priority_score.desc(), Recommendation.id)
    else:
        q = q.where(Recommendation.status.notin_([REC_AWAITING, REC_ADJUST, REC_INFO])).order_by(
            Recommendation.updated_at.desc(), Recommendation.id.desc()).limit(100)
    return [recommendation_out(r) for r in db.scalars(q)]


@router.post("/recommendations/{rec_id}/decision", response_model=RecommendationOut)
def decide(client_id: int, rec_id: int, body: DecisionIn, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    rec = db.get(Recommendation, rec_id, with_for_update=True)
    if rec is None or rec.client_id != client.id:
        raise HTTPException(404, "Recomendação não encontrada.")
    executor.decide(db, rec, client, user, body.decision, body.comment)
    db.commit()
    db.refresh(rec)
    return recommendation_out(rec)
