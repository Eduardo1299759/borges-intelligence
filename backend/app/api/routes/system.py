from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import AGENTS
from app.api.deps import current_user
from app.connectors.registry import INTEGRATIONS
from app.core.db import get_db
from app.models import AuditLog, User
from app.services import audit
from app.services.access import accessible_client_ids, require_role

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/agents")
def agents(_: User = Depends(current_user)):
    return AGENTS


@router.get("/integrations")
def integrations(_: User = Depends(current_user)):
    return INTEGRATIONS


@router.get("/audit")
def audit_log(client_id: int | None = None, limit: int = Query(100, ge=1, le=500),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    allowed = accessible_client_ids(db, user)
    if client_id is not None:
        q = q.where(AuditLog.client_id == (client_id if client_id in allowed else -1))
    elif user.role != "admin":
        q = q.where(AuditLog.client_id.in_(allowed))
    return [
        {"id": e.id, "ts": e.ts, "actor": e.actor_label, "client_id": e.client_id, "action": e.action,
         "entity_type": e.entity_type, "entity_id": e.entity_id, "details": e.details, "hash": e.hash}
        for e in db.scalars(q)
    ]


@router.get("/audit/verify")
def audit_verify(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin")
    return audit.verify_chain(db)
