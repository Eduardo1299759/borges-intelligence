"""Trilha de auditoria somente-inserção com cadeia de hash.

Cada registro inclui o hash do anterior; alterar ou remover qualquer linha quebra a cadeia e é
detectado por `verify_chain`. No PostgreSQL, a migração também instala um gatilho que bloqueia
UPDATE/DELETE na tabela. Isso torna adulteração evidente; não impede um superusuário do banco.
"""
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLog, User

GENESIS = "0" * 64


def _digest(prev_hash: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def _body(e: AuditLog) -> dict[str, Any]:
    return {
        "ts": e.ts,
        "actor_user_id": e.actor_user_id,
        "actor_label": e.actor_label,
        "client_id": e.client_id,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "details": e.details,
    }


def record(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    actor_label: str | None = None,
    client_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Adiciona um registro na transação corrente (commit é responsabilidade de quem chama)."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7300001)"))  # serializa a cadeia entre processos
    db.flush()
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    entry = AuditLog(
        ts=datetime.now(UTC).isoformat(),
        actor_user_id=actor.id if actor else None,
        actor_label=actor_label or (actor.email if actor else "sistema"),
        client_id=client_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.loads(json.dumps(details or {}, default=str)),
        prev_hash=prev,
        hash="",
    )
    entry.hash = _digest(prev, _body(entry))
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> dict[str, Any]:
    prev = GENESIS
    count = 0
    # populate_existing: sempre relê do banco, ignorando objetos em cache na sessão.
    stmt = select(AuditLog).order_by(AuditLog.id).execution_options(populate_existing=True)
    for e in db.scalars(stmt):
        if e.prev_hash != prev or e.hash != _digest(prev, _body(e)):
            return {"valid": False, "entries": count, "broken_at_id": e.id}
        prev = e.hash
        count += 1
    return {"valid": True, "entries": count, "broken_at_id": None}
