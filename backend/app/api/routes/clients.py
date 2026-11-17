from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.connectors.demo import HISTORY_DAYS, DemoConnector
from app.core.db import get_db
from app.models import Client, User, UserClientAccess
from app.schemas import ClientCreate, ClientOut, ClientUpdate
from app.services import audit
from app.services.access import accessible_client_ids, get_client_or_404, require_role
from app.services.ingestion import ingest

router = APIRouter(prefix="/clients", tags=["clients"])


def load_demo_data(db: Session, client: Client) -> dict[str, int]:
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS)
    connector = DemoConnector(seed=f"client-{client.id}", today=today, currency=client.currency)
    return ingest(db, client, connector, connector.fetch(start, today), start, today)


@router.get("", response_model=list[ClientOut])
def list_clients(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = accessible_client_ids(db, user)
    return db.scalars(select(Client).where(Client.id.in_(ids), Client.is_active).order_by(Client.name)).all()


@router.post("", response_model=ClientOut, status_code=201)
def create_client(body: ClientCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = Client(**body.model_dump())
    db.add(client)
    db.flush()
    db.add(UserClientAccess(user_id=user.id, client_id=client.id))
    stats = load_demo_data(db, client) if client.data_mode == "demo" else None
    audit.record(db, action="client.created", actor=user, client_id=client.id, entity_type="client",
                 entity_id=client.id, details={"name": client.name, "data_mode": client.data_mode, "demo": stats})
    db.commit()
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_client_or_404(db, user, client_id)


@router.put("/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientUpdate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    require_role(user, "admin", "manager")
    client = get_client_or_404(db, user, client_id)
    changes = {}
    for field, value in body.model_dump().items():
        old = getattr(client, field)
        if old != value:
            changes[field] = {"from": old, "to": value}
            setattr(client, field, value)
    if changes:
        audit.record(db, action="client.updated", actor=user, client_id=client.id, entity_type="client",
                     entity_id=client.id, details=changes)
    db.commit()
    return client
