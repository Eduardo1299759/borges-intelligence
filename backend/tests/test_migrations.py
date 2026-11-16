"""As migrações Alembic precisam produzir o mesmo esquema dos modelos, e proteger a auditoria."""
import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import get_settings
from app.core.db import Base


def test_migrations_match_models(tmp_path, monkeypatch):
    pg = os.environ.get("BORGES_TEST_DATABASE_URL", "")
    url = pg or f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("BORGES_DATABASE_URL", url)
    get_settings.cache_clear()
    engine = create_engine(url)
    try:
        if pg:
            Base.metadata.drop_all(engine)
            with engine.begin() as c:
                c.execute(text("DROP TABLE IF EXISTS alembic_version"))
                c.execute(text("DROP FUNCTION IF EXISTS audit_log_immutable() CASCADE"))
        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []
        if pg:
            with engine.begin() as c:
                c.execute(text(
                    "INSERT INTO audit_log (ts, actor_label, action, details, prev_hash, hash) "
                    "VALUES ('t', 'x', 'a', '{}', 'p', 'h')"))
            for stmt in ("UPDATE audit_log SET action = 'b'", "DELETE FROM audit_log"):
                with pytest.raises(DBAPIError, match="somente-inserção"), engine.begin() as c:
                    c.execute(text(stmt))
        command.downgrade(cfg, "base")
    finally:
        engine.dispose()
        get_settings.cache_clear()
