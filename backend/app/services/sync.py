"""Sincronização: escolhe o conector do cliente, busca, grava, reconcilia e registra o resultado.

Síncrona nesta fase (uma requisição = uma sincronização). O agendador e a fila entram na Fase 6.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ReadConnector
from app.connectors.demo import DemoConnector
from app.connectors.windsor import WindsorClient, WindsorConnector, WindsorError
from app.core import crypto
from app.core.config import get_settings
from app.models import Client, Integration, SyncRun, User
from app.services import audit
from app.services.ingestion import ingest, reconcile_levels

log = logging.getLogger(__name__)


class SyncUnavailable(Exception):
    pass


def get_integration(db: Session, client: Client, provider: str = "windsor") -> Integration | None:
    return db.scalar(select(Integration).where(Integration.client_id == client.id, Integration.provider == provider))


def windsor_connector(client: Client, integration: Integration) -> WindsorConnector:
    api_key = crypto.decrypt(integration.credentials_encrypted)
    allowed = get_settings().allowed_accounts()
    accounts = [a for a in integration.accounts or [] if allowed is None or a["external_id"] in allowed]
    return WindsorConnector(WindsorClient(api_key), accounts, currency=client.currency)


def _connector_for(db: Session, client: Client) -> tuple[ReadConnector, Integration | None]:
    if client.data_mode == "demo":
        return DemoConnector(seed=f"client-{client.id}", currency=client.currency), None
    integration = get_integration(db, client)
    if integration is None:
        raise SyncUnavailable("Nenhuma integração configurada para este cliente.")
    if not integration.accounts:
        raise SyncUnavailable("Selecione ao menos uma conta de anúncios antes de sincronizar.")
    return windsor_connector(client, integration), integration


def run_sync(db: Session, client: Client, user: User | None, days: int, actor_label: str | None = None) -> SyncRun:
    end = date.today()
    start = end - timedelta(days=days)
    connector, integration = _connector_for(db, client)
    run = SyncRun(client_id=client.id, provider=connector.source, period_start=start, period_end=end,
                  triggered_by=actor_label or (user.email if user else "sistema"))
    db.add(run)
    db.commit()  # o estado "executando" fica visível e sobrevive a uma falha posterior
    try:
        payload = connector.fetch(start, end)
        run.stats = ingest(db, client, connector, payload, start, end)
        run.issues = payload.issues + reconcile_levels(payload)
        if not payload.metrics:
            run.issues = run.issues + ["A fonte não retornou nenhuma linha para as contas e o período pedidos."]
        run.status = "completed"
        if integration:
            integration.status, integration.last_error = "connected", None
            integration.last_synced_at = datetime.now(UTC)
    except (WindsorError, crypto.EncryptionUnavailable) as exc:
        db.rollback()
        run = db.get(SyncRun, run.id)
        run.status, run.error = "failed", str(exc)
        if integration:
            integration = db.get(Integration, integration.id)
            integration.status, integration.last_error = "error", str(exc)
        log.warning("sync failed client=%s provider=%s: %s", client.id, connector.source, exc)
    run.finished_at = datetime.now(UTC)
    audit.record(db, action=f"sync.{run.status}", actor=user, actor_label=actor_label, client_id=client.id,
                 entity_type="sync_run", entity_id=run.id,
                 details={"provider": run.provider, "period": f"{start} a {end}", "stats": run.stats,
                          "issues": len(run.issues or []), "error": run.error})
    db.commit()
    return run
