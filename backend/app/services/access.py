"""Isolamento entre clientes: toda leitura de dados de cliente passa por estas funções."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, User, UserClientAccess


def accessible_client_ids(db: Session, user: User) -> list[int]:
    if user.role == "admin":
        return list(db.scalars(select(Client.id)))
    return list(db.scalars(select(UserClientAccess.client_id).where(UserClientAccess.user_id == user.id)))


def get_client_or_404(db: Session, user: User, client_id: int) -> Client:
    client = db.get(Client, client_id)
    allowed = client is not None and (
        user.role == "admin"
        or db.get(UserClientAccess, {"user_id": user.id, "client_id": client_id}) is not None
    )
    if not allowed:
        # 404 também para "sem acesso": não revela a existência de clientes de terceiros.
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return client


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Seu papel não permite esta operação.")
