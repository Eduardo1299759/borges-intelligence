"""Configuração por ambiente. Nenhum segredo fica no código: tudo vem de variáveis BORGES_*."""
from functools import lru_cache
from secrets import token_urlsafe

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BORGES_", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "sqlite:///./borges.db"
    secret_key: str = ""
    access_token_minutes: int = 480
    cookie_name: str = "borges_session"
    cookie_secure: bool = False
    # Usados apenas por `python -m app.cli seed` para criar o primeiro administrador.
    admin_email: str = ""
    admin_password: str = ""

    def resolved_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        if self.env == "production":
            raise RuntimeError("BORGES_SECRET_KEY é obrigatória em produção.")
        return _ephemeral_key()


@lru_cache
def _ephemeral_key() -> str:
    # Em desenvolvimento, sem chave configurada, as sessões expiram a cada reinício do processo.
    return token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
