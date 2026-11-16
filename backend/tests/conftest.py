import os

os.environ.setdefault("BORGES_ENV", "test")
os.environ.setdefault("BORGES_SECRET_KEY", "test-secret-key-not-for-production-0123456789")
# Por padrão os testes usam SQLite em memória; defina BORGES_TEST_DATABASE_URL para rodar em PostgreSQL.
os.environ["BORGES_DATABASE_URL"] = os.environ.get("BORGES_TEST_DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core import db as db_module  # noqa: E402
from app.core.db import Base, get_db, make_engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

PASSWORD = "senha-de-teste-123"
_PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture()
def session_factory():
    url = os.environ["BORGES_DATABASE_URL"]
    if url.startswith("sqlite"):
        from sqlalchemy import create_engine, event

        engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    else:
        engine = make_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db_module.SessionLocal = factory

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    with session_factory() as session:
        yield session


def make_user(db, email: str, role: str) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash=_PASSWORD_HASH)
    db.add(user)
    db.commit()
    return user


def login(email: str) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def admin(db) -> TestClient:
    make_user(db, "admin@example.com", "admin")
    return login("admin@example.com")


DEMO_CLIENT = {"name": "Cliente Demo", "data_mode": "demo", "target_cac": "25", "target_roas": "4",
               "gross_margin_pct": "35"}


@pytest.fixture()
def demo_client(admin) -> dict:
    r = admin.post("/api/clients", json=DEMO_CLIENT)
    assert r.status_code == 201, r.text
    return r.json()
