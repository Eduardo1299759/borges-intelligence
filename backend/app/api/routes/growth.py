"""Fase 4: Creative Studio (criativos e briefings), Experimentos e Radar competitivo."""
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes.insights import resolve_period
from app.competitive import service as competitive
from app.core.db import get_db
from app.creative import briefs as brief_service
from app.creative.library import library
from app.experiments import service as experiments
from app.experiments.service import METRIC_LABEL
from app.models import Ad, Campaign, Competitor, CompetitorAd, CreativeBrief, Experiment, Recommendation, User
from app.services import audit
from app.services.access import get_client_or_404, require_role

router = APIRouter(prefix="/clients/{client_id}", tags=["growth"])
EDITORS = ("admin", "manager", "analyst")


# --- Creative Studio --------------------------------------------------------------------------------

@router.get("/creatives")
def creatives(client_id: int, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    start, end = resolve_period(db, client, days)
    return {"period": {"start": start, "end": end}, "is_demo": client.data_mode == "demo",
            "creatives": library(db, client, start, end)}


class BriefIn(BaseModel):
    objective: str = Field(min_length=3, max_length=500)
    audience: str = Field(min_length=3, max_length=500)
    offer: str = Field(min_length=3, max_length=1000)
    angle: str | None = Field(default=None, max_length=300)
    ad_id: int | None = None
    recommendation_id: int | None = None
    variations: int = Field(default=4, ge=3, le=5)


def _brief_out(b: CreativeBrief) -> dict:
    return {c.name: getattr(b, c.name) for c in CreativeBrief.__table__.columns}


@router.get("/briefs")
def list_briefs(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rows = db.scalars(select(CreativeBrief).where(CreativeBrief.client_id == client.id)
                      .order_by(CreativeBrief.id.desc()).limit(30))
    return [_brief_out(b) for b in rows]


@router.post("/briefs", status_code=201)
def create_brief(client_id: int, body: BriefIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    reference, rec_facts, campaign_id = None, None, None
    if body.ad_id is not None:
        ad = db.get(Ad, body.ad_id)
        if ad is None or ad.client_id != client.id:
            raise HTTPException(404, "Anúncio não encontrado.")
        start, end = resolve_period(db, client, 30)
        reference = next((c for c in library(db, client, start, end) if c["ad_id"] == ad.id), None)
        campaign_id = ad.campaign_id
    if body.recommendation_id is not None:
        rec = db.get(Recommendation, body.recommendation_id)
        if rec is None or rec.client_id != client.id:
            raise HTTPException(404, "Recomendação não encontrada.")
        rec_facts = {"titulo": rec.title, "problema": rec.problem, "hipotese": rec.hypothesis}
        campaign_id = campaign_id or rec.campaign_id
    facts = brief_service.facts_for(client, body.objective, body.audience, body.offer, body.angle, reference, rec_facts)
    variations, source, model, note = brief_service.generate(db, client, facts, body.variations)
    brief = CreativeBrief(client_id=client.id, campaign_id=campaign_id, ad_id=body.ad_id,
                          recommendation_id=body.recommendation_id, objective=body.objective, audience=body.audience,
                          offer=body.offer, angle=body.angle, hypothesis=rec_facts["hipotese"] if rec_facts else None,
                          variations=variations, source=source, ai_model=model, note=note, created_by=user.id)
    db.add(brief)
    db.flush()
    audit.record(db, action="creative.brief_created", actor=user, client_id=client.id, entity_type="creative_brief",
                 entity_id=brief.id, details={"source": source, "variations": len(variations), "ad_id": body.ad_id})
    db.commit()
    return _brief_out(brief)


# --- Experimentos -----------------------------------------------------------------------------------

class ExperimentIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    problem: str = Field(min_length=3, max_length=2000)
    hypothesis: str = Field(min_length=3, max_length=2000)
    variable: str = Field(min_length=2, max_length=200)
    primary_metric: Literal["lead_rate", "cpl"] = "lead_rate"
    guardrails: list[str] = Field(default_factory=lambda: ["CTR", "Custo por clique", "Taxa lead → venda (CRM)"],
                                  max_length=8)
    control_ad_ids: list[int] = Field(min_length=1, max_length=20)
    variant_ad_ids: list[int] = Field(min_length=1, max_length=20)
    relative_mde_pct: float = Field(default=20, ge=5, le=100)
    planned_days: int = Field(default=14, ge=3, le=90)
    recommendation_id: int | None = None
    brief_id: int | None = None


class StartIn(BaseModel):
    # Uma data passada faz uma análise retroativa sobre dados que já existem.
    start_date: date | None = None


class ConcludeIn(BaseModel):
    outcome: Literal["success", "failure", "inconclusive"]
    learning: str = Field(min_length=10, max_length=3000)


def _exp_out(db: Session, client, e: Experiment, with_eval: bool = True) -> dict:
    ad_names = {a.id: a.name for a in db.scalars(select(Ad).where(Ad.id.in_(e.control_ad_ids + e.variant_ad_ids)))}
    campaign = db.get(Campaign, e.campaign_id) if e.campaign_id else None
    out = {c.name: getattr(e, c.name) for c in Experiment.__table__.columns}
    out.update(campaign_name=campaign.name if campaign else None, primary_metric_label=METRIC_LABEL[e.primary_metric],
               control_ads=[ad_names.get(i) for i in e.control_ad_ids],
               variant_ads=[ad_names.get(i) for i in e.variant_ad_ids],
               retroactive=bool(e.start_date and e.start_date < e.created_at.date()))
    if with_eval:
        out["evaluation"] = e.final_result if e.status == "concluded" else experiments.evaluation(db, client, e)
    return out


def _get_exp(db: Session, client, exp_id: int) -> Experiment:
    e = db.get(Experiment, exp_id)
    if e is None or e.client_id != client.id:
        raise HTTPException(404, "Experimento não encontrado.")
    return e


@router.get("/experiments")
def list_experiments(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rows = db.scalars(select(Experiment).where(Experiment.client_id == client.id).order_by(Experiment.id.desc()))
    return [_exp_out(db, client, e) for e in rows]


@router.post("/experiments", status_code=201)
def create_experiment(client_id: int, body: ExperimentIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    campaign_id = experiments.validate_ads(db, client, body.control_ad_ids, body.variant_ad_ids)
    for ref_id, model, label in ((body.recommendation_id, Recommendation, "Recomendação"),
                                 (body.brief_id, CreativeBrief, "Briefing")):
        if ref_id is not None:
            ref = db.get(model, ref_id)
            if ref is None or ref.client_id != client.id:
                raise HTTPException(404, f"{label} não encontrado(a).")
    e = Experiment(client_id=client.id, campaign_id=campaign_id, created_by=user.id,
                   is_demo=client.data_mode == "demo", **body.model_dump())
    db.add(e)
    db.flush()
    audit.record(db, action="experiment.created", actor=user, client_id=client.id, entity_type="experiment",
                 entity_id=e.id, details={"name": e.name, "control": e.control_ad_ids, "variant": e.variant_ad_ids})
    db.commit()
    return _exp_out(db, client, e)


@router.get("/experiments/{exp_id}")
def get_experiment(client_id: int, exp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    return _exp_out(db, client, _get_exp(db, client, exp_id))


@router.post("/experiments/{exp_id}/start")
def start_experiment(client_id: int, exp_id: int, body: StartIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    e = _get_exp(db, client, exp_id)
    if e.status != "draft":
        raise HTTPException(409, "Só experimentos em rascunho podem ser iniciados.")
    e.start_date = body.start_date or date.today()
    if e.start_date > date.today() + timedelta(days=30):
        raise HTTPException(422, "Data de início muito distante.")
    e.status = "running"
    audit.record(db, action="experiment.started", actor=user, client_id=client.id, entity_type="experiment",
                 entity_id=e.id, details={"start_date": e.start_date})
    db.commit()
    return _exp_out(db, client, e)


@router.post("/experiments/{exp_id}/conclude")
def conclude_experiment(client_id: int, exp_id: int, body: ConcludeIn, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    e = _get_exp(db, client, exp_id)
    if e.status != "running":
        raise HTTPException(409, "Só experimentos em andamento podem ser concluídos.")
    experiments.conclude(db, client, e, body.outcome, body.learning)
    audit.record(db, action="experiment.concluded", actor=user, client_id=client.id, entity_type="experiment",
                 entity_id=e.id, details={"outcome": body.outcome, "learning": body.learning,
                                          "verdict": (e.final_result or {}).get("verdict", {}).get("status")})
    db.commit()
    return _exp_out(db, client, e)


@router.post("/experiments/{exp_id}/cancel")
def cancel_experiment(client_id: int, exp_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    e = _get_exp(db, client, exp_id)
    if e.status not in ("draft", "running"):
        raise HTTPException(409, "Este experimento já foi encerrado.")
    e.status = "cancelled"
    audit.record(db, action="experiment.cancelled", actor=user, client_id=client.id, entity_type="experiment",
                 entity_id=e.id, details={})
    db.commit()
    return _exp_out(db, client, e)


# --- Radar competitivo ------------------------------------------------------------------------------

def _http_url(v: str | None) -> str | None:
    """Links viram <a href> no painel: só http(s), nunca javascript: ou data:."""
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not v.lower().startswith(("http://", "https://")):
        raise ValueError("O link precisa começar com http:// ou https://.")
    return v


class CompetitorIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    website: str | None = Field(default=None, max_length=300)
    facebook_page: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)

    _links = field_validator("website", "facebook_page")(classmethod(lambda cls, v: _http_url(v)))


class CompetitorAdIn(BaseModel):
    ad_text: str = Field(min_length=3, max_length=5000)
    url: str | None = Field(default=None, max_length=500)
    offer: str | None = Field(default=None, max_length=500)
    format: Literal["imagem", "video", "carrossel", "outro"] | None = None
    first_seen: date | None = None

    _link = field_validator("url")(classmethod(lambda cls, v: _http_url(v)))


@router.get("/radar")
def radar(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return competitive.overview(db, get_client_or_404(db, user, client_id))


@router.post("/competitors", status_code=201)
def add_competitor(client_id: int, body: CompetitorIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    c = Competitor(client_id=client.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, action="competitor.added", actor=user, client_id=client.id, entity_type="competitor",
                 entity_id=c.id, details={"name": c.name})
    db.commit()
    return {"id": c.id, "name": c.name}


@router.delete("/competitors/{competitor_id}", status_code=204)
def remove_competitor(client_id: int, competitor_id: int, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    c = db.get(Competitor, competitor_id)
    if c is None or c.client_id != client.id:
        raise HTTPException(404, "Concorrente não encontrado.")
    audit.record(db, action="competitor.removed", actor=user, client_id=client.id, entity_type="competitor",
                 entity_id=c.id, details={"name": c.name})
    db.delete(c)
    db.commit()


@router.post("/competitors/{competitor_id}/ads", status_code=201)
def add_competitor_ad(client_id: int, competitor_id: int, body: CompetitorAdIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    c = db.get(Competitor, competitor_id)
    if c is None or c.client_id != client.id:
        raise HTTPException(404, "Concorrente não encontrado.")
    if body.first_seen and body.first_seen > date.today():
        raise HTTPException(422, "A data em que o anúncio foi visto não pode estar no futuro.")
    ad = CompetitorAd(client_id=client.id, competitor_id=c.id, source="manual", **body.model_dump())
    db.add(ad)
    db.commit()
    return {"id": ad.id}


@router.post("/radar/insights")
def radar_insights(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, *EDITORS)
    client = get_client_or_404(db, user, client_id)
    out = competitive.insights(db, client)
    db.commit()  # registra o uso da IA
    return out
