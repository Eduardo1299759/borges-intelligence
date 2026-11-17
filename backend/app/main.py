from fastapi import APIRouter, FastAPI

from app.api.routes import ai, auth, clients, growth, insights, integrations, intelligence, system
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    get_settings().resolved_secret_key()  # falha cedo se faltar a chave em produção
    app = FastAPI(title="Borges Intelligence API", version="0.1.0")
    api = APIRouter(prefix="/api")
    for module in (system, auth, clients, insights, intelligence, integrations, ai, growth):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
