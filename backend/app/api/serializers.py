from app.models import Recommendation
from app.schemas import DecisionOut, ExecutionOut, RecommendationOut


def recommendation_out(r: Recommendation) -> RecommendationOut:
    data = {c.name: getattr(r, c.name) for c in Recommendation.__table__.columns}
    return RecommendationOut(
        **data,
        campaign_name=r.campaign.name if r.campaign else None,
        platform=r.campaign.platform if r.campaign else None,
        decisions=[DecisionOut(decision=d.decision, comment=d.comment, user=d.user.name if d.user else None,
                               created_at=d.created_at) for d in r.decisions],
        executions=[ExecutionOut.model_validate(e) for e in r.executions],
    )
