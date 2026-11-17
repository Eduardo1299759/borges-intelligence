"""Fase 5: vendas e CRM (importação e funil), Tracking & CRO, execuções reais e chave de escrita."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.routes.insights import resolve_period
from app.core.db import get_db
from app.execution import executor
from app.models import ImportRun, Integration, PageCheck, User
from app.sales import importer, intelligence
from app.schemas import ExecutionOut
from app.services import audit
from app.services.access import get_client_or_404, require_role
from app.tracking import audit as tracking_audit
from app.tracking import page_check

router = APIRouter(prefix="/clients/{client_id}", tags=["commercial"])

MAX_CSV_CHARS = 20_000_000


class ImportIn(BaseModel):
    kind: Literal["orders", "leads"]
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_CHARS)
    commit: bool = False  # False = só prévia


@router.post("/imports")
def import_csv(client_id: int, body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    if client.data_mode == "demo" and body.commit:
        raise HTTPException(409, "Clientes de demonstração já têm vendas simuladas; importe em um cliente real.")
    fn = importer.import_orders if body.kind == "orders" else importer.import_leads
    try:
        result = fn(db, client, body.csv_text, commit=body.commit).as_dict()
    except importer.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.commit:
        db.add(ImportRun(client_id=client.id, kind=body.kind, stats=result, created_by=user.id))
        audit.record(db, action=f"import.{body.kind}", actor=user, client_id=client.id,
                     details={k: result[k] for k in ("rows_read", "imported", "skipped", "totals",
                                                     "ignored_personal_columns")})
        db.commit()
    else:
        db.rollback()
    return {"committed": body.commit, **result}


@router.get("/imports")
def list_imports(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    rows = db.scalars(select(ImportRun).where(ImportRun.client_id == client.id).order_by(ImportRun.id.desc()).limit(20))
    return [{"id": r.id, "kind": r.kind, "stats": r.stats, "created_at": r.created_at} for r in rows]


@router.get("/sales")
def sales(client_id: int, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    start, end = resolve_period(db, client, days)
    return intelligence.summary(db, client, start, end)


class PageCheckIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


@router.post("/tracking/page-check", status_code=201)
def run_page_check(client_id: int, body: PageCheckIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_role(user, "admin", "manager", "analyst")
    client = get_client_or_404(db, user, client_id)
    try:
        result = page_check.check(body.url)
    except page_check.PageCheckError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(PageCheck(client_id=client.id, url=body.url.strip()[:500], result=result))
    db.commit()
    return result


@router.get("/tracking")
def tracking(client_id: int, days: int = Query(30, ge=7, le=90), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    client = get_client_or_404(db, user, client_id)
    start, end = resolve_period(db, client, days)
    checks = db.scalars(select(PageCheck).where(PageCheck.client_id == client.id).order_by(PageCheck.id.desc())
                        .limit(10))
    return {"findings": tracking_audit.findings(db, client, start, end),
            "utm": tracking_audit.utm_suggestions(db, client),
            "page_checks": [{"id": c.id, "url": c.url, "created_at": c.created_at, "result": c.result} for c in checks]}


# --- execuções reais: segunda confirmação e verificação ---------------------------------------------

@router.post("/executions/{execution_id}/confirm", response_model=ExecutionOut)
def confirm_execution(client_id: int, execution_id: int, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    execution = executor.confirm(db, client, user, execution_id)
    db.commit()
    return execution


@router.post("/executions/{execution_id}/verify", response_model=ExecutionOut)
def verify_execution(client_id: int, execution_id: int, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    execution = executor.verify(db, client, user, execution_id)
    db.commit()
    return execution


class WriteAccessIn(BaseModel):
    enabled: bool
    # Para ligar, o administrador digita o nome do cliente: evita ligar a escrita real por engano.
    confirm_name: str | None = None


@router.put("/write-access")
def write_access(client_id: int, body: WriteAccessIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    require_role(user, "admin")
    client = get_client_or_404(db, user, client_id)
    if body.enabled:
        if client.data_mode != "live":
            raise HTTPException(409, "Escrita real só existe para clientes reais.")
        integration = db.scalar(select(Integration).where(Integration.client_id == client.id,
                                                          Integration.provider == "windsor"))
        if integration is None or integration.status != "connected":
            raise HTTPException(409, "Conecte e teste o Windsor.ai antes de ligar a escrita.")
        if (body.confirm_name or "").strip() != client.name:
            raise HTTPException(422, "Digite exatamente o nome do cliente para confirmar.")
    client.write_enabled = body.enabled
    audit.record(db, action="client.write_access_" + ("enabled" if body.enabled else "disabled"), actor=user,
                 client_id=client.id, entity_type="client", entity_id=client.id, details={})
    db.commit()
    return {"write_enabled": client.write_enabled}
