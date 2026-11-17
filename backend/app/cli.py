"""Comandos administrativos.

  python -m app.cli init-env [--accounts IDS]    cria o backend/.env com chaves geradas (instalação local)
  python -m app.cli login-info                   mostra o login inicial (se ainda não foi trocado)
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
from app.core.security import hash_password, verify_password
from app.models import ROLES, Client, User, UserClientAccess
from app.services import audit

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def init_env(accounts: str | None) -> None:
    """Cria o .env local a partir do .env.example, gerando as chaves. Nunca sobrescreve um .env existente."""
    from cryptography.fernet import Fernet

    if not ENV_FILE.exists():
        generated = {
            "BORGES_SECRET_KEY": secrets.token_urlsafe(48),
            "BORGES_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "BORGES_ADMIN_PASSWORD": secrets.token_urlsafe(12),
            "BORGES_WINDSOR_ALLOWED_ACCOUNTS": (accounts or "").replace(" ", ""),
        }
        lines = []
        for line in (ENV_FILE.parent / ".env.example").read_text(encoding="utf-8").splitlines():
            key = line.partition("=")[0].strip()
            lines.append(f"{key}={generated.pop(key)}" if key in generated else line)
        lines += [f"{k}={v}" for k, v in generated.items()]
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Arquivo de configuração criado: {ENV_FILE}")
    else:
        print(f"Arquivo de configuração já existe (mantido): {ENV_FILE}")
    values = _read_env(ENV_FILE)
    if values.get("BORGES_ADMIN_PASSWORD"):
        print(f"Login do painel: {values.get('BORGES_ADMIN_EMAIL') or 'admin@borges.local'}"
              f" / senha: {values['BORGES_ADMIN_PASSWORD']}")


def login_info() -> None:
    """Mostra o login inicial, ou avisa que ele já foi trocado pelo usuário no painel."""
    values = _read_env(ENV_FILE) if ENV_FILE.exists() else {}
    email = (values.get("BORGES_ADMIN_EMAIL") or "admin@borges.local").lower()
    password = values.get("BORGES_ADMIN_PASSWORD") or ""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and password and verify_password(password, user.password_hash):
            print(f"Login do painel: {email} / senha: {password}")
        else:
            print("Login do painel: o que você definiu em Configurações > Minha conta.")


def wait_api(url: str = "http://127.0.0.1:8000/api/health", seconds: int = 60) -> bool:
    """Espera a API local responder (usado pelo instalador antes de abrir o navegador)."""
    import time
    import urllib.request

    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    print("API respondendo.")
                    return True
        except OSError:
            pass
        time.sleep(1)
    print("A API não respondeu em 60 segundos.")
    return False


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
    ie = sub.add_parser("init-env")
    ie.add_argument("--accounts", default=None, help="IDs de contas Windsor.ai permitidas, separados por vírgula")
    sub.add_parser("login-info")
    wa = sub.add_parser("wait-api")
    wa.add_argument("url", nargs="?", default="http://127.0.0.1:8000/api/health")
    wa.add_argument("--seconds", type=int, default=60)
    sub.add_parser("init-db")
    sub.add_parser("seed")
    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("name")
    cu.add_argument("role", choices=ROLES)
    args = parser.parse_args()
    if args.cmd == "init-env":
        init_env(args.accounts)
    elif args.cmd == "login-info":
        login_info()
    elif args.cmd == "wait-api":
        sys.exit(0 if wait_api(args.url, args.seconds) else 1)
    elif args.cmd == "init-db":
        init_db()
    elif args.cmd == "seed":
        seed()
    else:
        create_user(args.email, args.name, args.role)


if __name__ == "__main__":
    main()
