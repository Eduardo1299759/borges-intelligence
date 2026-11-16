from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = hash_password("borges-timing-equalizer")


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    # Verifica sempre um hash, mesmo sem usuário, para não revelar e-mails válidos pelo tempo de resposta.
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid or not user.is_active:
        audit.record(db, action="auth.login_failed", actor_label=body.email.lower(), details={})
        db.commit()
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    response.set_cookie(s.cookie_name, create_access_token(user.id), httponly=True, samesite="lax",
                        secure=s.cookie_secure, max_age=s.access_token_minutes * 60, path="/")
    audit.record(db, action="auth.login", actor=user, details={})
    db.commit()
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
