"""Integração Windsor.ai por cliente e sincronização de dados.

A chave de API entra uma vez, é cifrada e nunca mais sai pela API (apenas os 4 últimos caracteres).
"""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.connectors.windsor import WindsorClient, WindsorConnector, WindsorError
from app.core import crypto
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Client, Integration, SyncRun, User
from app.schemas import AccountsIn, SyncIn, WindsorKeyIn
from app.services import audit, sync
from app.services.access import get_client_or_404, require_role

router = APIRouter(prefix="/clients/{client_id}", tags=["integrations"])


def _out(client: Client, i: Integration | None) -> dict[str, Any]:
    if i is None:
        return {"provider": "windsor", "configured": False, "data_mode": client.data_mode}
    return {
        "provider": i.provider, "configured": True, "data_mode": client.data_mode, "status": i.status,
        "key_hint": i.key_hint, "accounts": i.accounts or [], "last_error": i.last_error,
        "last_checked_at": i.last_checked_at, "last_synced_at": i.last_synced_at,
    }


def _run_out(r: SyncRun) -> dict[str, Any]:
    return {"id": r.id, "provider": r.provider, "status": r.status, "period_start": r.period_start,
            "period_end": r.period_end, "stats": r.stats, "issues": r.issues or [], "error": r.error,
            "triggered_by": r.triggered_by, "started_at": r.started_at, "finished_at": r.finished_at}


def _live_client(db: Session, user: User, client_id: int) -> Client:
    client = get_client_or_404(db, user, client_id)
    if client.data_mode != "live":
        raise HTTPException(409, "Clientes de demonstração não recebem integrações reais.")
    return client


def _integration_or_404(db: Session, client: Client) -> Integration:
    integration = sync.get_integration(db, client)
    if integration is None:
        raise HTTPException(404, "Integração Windsor.ai não configurada para este cliente.")
    return integration


@router.get("/integration")
def get_integration(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    return _out(client, sync.get_integration(db, client))


@router.put("/integration/windsor")
def connect_windsor(client_id: int, body: WindsorKeyIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Salva a chave (cifrada) e testa a conexão imediatamente. O resultado do teste fica no status."""
    require_role(user, "admin", "manager")
    client = _live_client(db, user, client_id)
    try:
        encrypted = crypto.encrypt(body.api_key)
    except crypto.EncryptionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    integration = sync.get_integration(db, client)
    if integration is None:
        integration = Integration(client_id=client.id, provider="windsor", credentials_encrypted=encrypted,
                                  key_hint=body.api_key[-4:], accounts=[])
        db.add(integration)
    else:
        integration.credentials_encrypted, integration.key_hint = encrypted, body.api_key[-4:]
    status = WindsorConnector(WindsorClient(body.api_key), [], currency=client.currency).check()
    integration.status = "connected" if status.ok else "error"
    integration.last_error = None if status.ok else status.detail
    integration.last_checked_at = datetime.now(UTC)
    db.flush()
    audit.record(db, action="integration.connected" if status.ok else "integration.check_failed", actor=user,
                 client_id=client.id, entity_type="integration", entity_id=integration.id,
                 details={"provider": "windsor", "key_hint": integration.key_hint, "detail": status.detail})
    db.commit()
    return {**_out(client, integration), "check": status.detail}


@router.get("/integration/windsor/accounts")
def discover_accounts(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = _live_client(db, user, client_id)
    integration = _integration_or_404(db, client)
    try:
        found = sync.windsor_connector(client, integration).discover_accounts(days=30)
    except (WindsorError, crypto.EncryptionUnavailable) as exc:
        raise HTTPException(502, str(exc)) from exc
    allowed = get_settings().allowed_accounts()
    return [a for a in found if allowed is None or a["external_id"] in allowed]


@router.put("/integration/windsor/accounts")
def select_accounts(client_id: int, body: AccountsIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = _live_client(db, user, client_id)
    integration = _integration_or_404(db, client)
    allowed = get_settings().allowed_accounts()
    outside = [a.external_id for a in body.accounts if allowed is not None and a.external_id not in allowed]
    if outside:
        raise HTTPException(422, f"Conta(s) fora do escopo permitido nesta instalação: {', '.join(outside)}.")
    unique = {(a.platform, a.external_id): a.model_dump() for a in body.accounts}
    integration.accounts = list(unique.values())
    audit.record(db, action="integration.accounts_selected", actor=user, client_id=client.id,
                 entity_type="integration", entity_id=integration.id, details={"accounts": integration.accounts})
    db.commit()
    return _out(client, integration)


@router.delete("/integration/windsor", status_code=204)
def disconnect_windsor(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Remove a credencial. Os dados já sincronizados permanecem como histórico."""
    require_role(user, "admin", "manager")
    client = _live_client(db, user, client_id)
    integration = _integration_or_404(db, client)
    audit.record(db, action="integration.removed", actor=user, client_id=client.id, entity_type="integration",
                 entity_id=integration.id, details={"provider": "windsor", "key_hint": integration.key_hint})
    db.delete(integration)
    db.commit()


@router.post("/sync", status_code=201)
def start_sync(client_id: int, body: SyncIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    running = db.scalar(select(SyncRun.id).where(SyncRun.client_id == client.id, SyncRun.status == "running"))
    if running is not None:
        raise HTTPException(409, "Já existe uma sincronização em andamento para este cliente.")
    try:
        return _run_out(sync.run_sync(db, client, user, body.days))
    except sync.SyncUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/sync-runs")
def sync_runs(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    runs = db.scalars(select(SyncRun).where(SyncRun.client_id == client.id).order_by(SyncRun.id.desc()).limit(20))
    return [_run_out(r) for r in runs]
