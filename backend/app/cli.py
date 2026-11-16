"""Comandos administrativos.

  python -m app.cli init-db                      aplica as migrações
  python -m app.cli seed                         cria o administrador inicial e um cliente demonstrativo
  python -m app.cli create-user EMAIL NOME PAPEL cria um usuário (senha solicitada no terminal)
"""
import argparse
import getpass
import secrets
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import ROLES, Client, User, UserClientAccess
from app.services import audit


def init_db() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


def seed() -> None:
    from app.api.routes.clients import load_demo_data

    s = get_settings()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == "admin"))
        if admin is None:
            email = (s.admin_email or "admin@borges.local").lower()
            password = s.admin_password or secrets.token_urlsafe(12)
            admin = User(email=email, name="Administrador", role="admin", password_hash=hash_password(password))
            db.add(admin)
            db.flush()
            audit.record(db, action="user.created", actor_label="cli", entity_type="user", entity_id=admin.id,
                         details={"email": email, "role": "admin"})
            print(f"Administrador criado: {email}")
            if not s.admin_password:
                print(f"Senha gerada (exibida apenas agora): {password}")
        else:
            print(f"Administrador já existe: {admin.email}")
        if db.scalar(select(Client.id).limit(1)) is None:
            client = Client(
                name="Sabor da Vila Delivery (DEMONSTRAÇÃO)", segment="Restaurante / delivery", data_mode="demo",
                business_goal="Aumentar pedidos rentáveis via WhatsApp e cardápio digital.",
                monthly_budget=Decimal("14000"), target_cac=Decimal("25"), target_roas=Decimal("4"),
                gross_margin_pct=Decimal("35"),
            )
            db.add(client)
            db.flush()
            db.add(UserClientAccess(user_id=admin.id, client_id=client.id))
            stats = load_demo_data(db, client)
            audit.record(db, action="client.created", actor_label="cli", client_id=client.id, entity_type="client",
                         entity_id=client.id, details={"name": client.name, "data_mode": "demo", "demo": stats})
            print(f"Cliente demonstrativo criado: {client.name} {stats}")
        db.commit()


def create_user(email: str, name: str, role: str) -> None:
    password = getpass.getpass("Senha (mín. 10 caracteres): ")
    if len(password) < 10:
        sys.exit("Senha muito curta.")
    with SessionLocal() as db:
        user = User(email=email.lower(), name=name, role=role, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        audit.record(db, action="user.created", actor_label="cli", entity_type="user", entity_id=user.id,
                     details={"email": user.email, "role": role})
        db.commit()
    print(f"Usuário criado: {email} ({role})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("seed")
    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("name")
    cu.add_argument("role", choices=ROLES)
    args = parser.parse_args()
    if args.cmd == "init-db":
        init_db()
    elif args.cmd == "seed":
        seed()
    else:
        create_user(args.email, args.name, args.role)


if __name__ == "__main__":
    main()
