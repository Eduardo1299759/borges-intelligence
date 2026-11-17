from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import CredentialsIn, LoginIn, UserOut
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


@router.put("/me/credentials", response_model=UserOut)
def change_credentials(body: CredentialsIn, response: Response, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Troca o próprio login e/ou senha. Exige a senha atual."""
    if not verify_password(body.current_password, user.password_hash):
        audit.record(db, action="auth.credentials_change_failed", actor=user, details={})
        db.commit()
        raise HTTPException(status_code=403, detail="Senha atual incorreta.")
    if body.new_login is None and body.new_password is None:
        raise HTTPException(status_code=422, detail="Informe um novo login, uma nova senha ou ambos.")
    changed = []
    if body.new_login is not None and body.new_login != user.email:
        if db.scalar(select(User.id).where(User.email == body.new_login, User.id != user.id)) is not None:
            raise HTTPException(status_code=409, detail="Este login já está em uso.")
        audit_from = user.email
        user.email = body.new_login
        changed.append({"field": "login", "from": audit_from, "to": body.new_login})
    if body.new_password is not None:
        user.password_hash = hash_password(body.new_password)
        changed.append({"field": "password"})  # a senha nunca vai para a auditoria
    audit.record(db, action="auth.credentials_changed", actor=user, details={"changes": changed})
    db.commit()
    s = get_settings()
    response.set_cookie(s.cookie_name, create_access_token(user.id), httponly=True, samesite="lax",
                        secure=s.cookie_secure, max_age=s.access_token_minutes * 60, path="/")
    return user
