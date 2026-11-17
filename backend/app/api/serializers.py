from app.models import Recommendation
from app.schemas import DecisionOut, ExecutionOut, RecommendationOut


def recommendation_out(r: Recommendation) -> RecommendationOut:
    data = {c.name: getattr(r, c.name) for c in Recommendation.__table__.columns}
    return RecommendationOut(
        **data,
        campaign_name=r.campaign.name if r.campaign else None,
        platform=r.campaign.platform if r.campaign else None,
        ad_set_name=r.ad_set.name if r.ad_set else None,
        ad_name=r.ad.name if r.ad else None,
        ad_status=r.ad.status if r.ad else None,
        decisions=[DecisionOut(decision=d.decision, comment=d.comment, user=d.user.name if d.user else None,
                               created_at=d.created_at) for d in r.decisions],
        executions=[ExecutionOut.model_validate(e) for e in r.executions],
    )
