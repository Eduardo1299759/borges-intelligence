"""Configuração e custos da IA (Anthropic). Só administradores alteram; gestores consultam o uso."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import pricing
from app.ai.settings import get_settings_row, month_spend
from app.api.deps import current_user
from app.core import crypto
from app.core.db import get_db
from app.models import AIUsage, User
from app.services import audit
from app.services.access import accessible_client_ids, require_role

router = APIRouter(prefix="/ai", tags=["ai"])


class AISettingsIn(BaseModel):
    enabled: bool
    model: Literal["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    effort: Literal["low", "medium", "high"]
    monthly_cap_usd: Decimal = Field(ge=0, le=10_000)
    api_key: str | None = Field(default=None, max_length=400)  # vazio = manter a chave atual


def _out(db: Session) -> dict:
    cfg = get_settings_row(db)
    return {
        "enabled": cfg.enabled, "configured": bool(cfg.api_key_encrypted), "key_hint": cfg.key_hint,
        "model": cfg.model, "effort": cfg.effort, "monthly_cap_usd": float(cfg.monthly_cap_usd),
        "month_spend_usd": float(month_spend(db)),
        "models": [{"id": m, "label": pricing.LABELS[m], "input_per_mtok": float(pricing.PRICES[m][0]),
                    "output_per_mtok": float(pricing.PRICES[m][1])} for m in pricing.SELECTABLE],
    }


@router.get("/settings")
def get_ai_settings(_: User = Depends(current_user), db: Session = Depends(get_db)):
    out = _out(db)
    db.commit()
    return out


@router.put("/settings")
def put_ai_settings(body: AISettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin")
    cfg = get_settings_row(db)
    key = (body.api_key or "").strip()
    if key:
        if any(ch.isspace() for ch in key) or len(key) < 20:
            raise HTTPException(422, "Chave de API em formato inválido.")
        try:
            cfg.api_key_encrypted = crypto.encrypt(key)
        except crypto.EncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        cfg.key_hint = key[-4:]
    if body.enabled and not cfg.api_key_encrypted:
        raise HTTPException(422, "Informe a chave de API da Anthropic antes de ativar a IA.")
    changes = {"enabled": body.enabled, "model": body.model, "effort": body.effort,
               "monthly_cap_usd": str(body.monthly_cap_usd), "key_changed": bool(key)}
    cfg.enabled, cfg.model, cfg.effort = body.enabled, body.model, body.effort
    cfg.monthly_cap_usd = body.monthly_cap_usd
    audit.record(db, action="ai.settings_updated", actor=user, details=changes)
    db.commit()
    return _out(db)


@router.get("/usage")
def ai_usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    q = select(AIUsage).order_by(AIUsage.id.desc()).limit(50)
    if user.role != "admin":
        q = q.where(AIUsage.client_id.in_(accessible_client_ids(db, user)))
    return [{"id": u.id, "created_at": u.created_at, "client_id": u.client_id, "model": u.model, "status": u.status,
             "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cost_usd": float(u.cost_usd),
             "detail": u.detail} for u in db.scalars(q)]
