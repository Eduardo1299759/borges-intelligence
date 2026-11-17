"""Configuração por ambiente. Nenhum segredo fica no código: tudo vem de variáveis BORGES_*."""
from functools import lru_cache
from secrets import token_urlsafe

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BORGES_", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "sqlite:///./borges.db"
    secret_key: str = ""
    # Chave Fernet para cifrar credenciais de integrações. Sem ela, credenciais não podem ser salvas.
    encryption_key: str = ""
    windsor_base_url: str = "https://connectors.windsor.ai"
    # Só para testes: aponta o SDK da Anthropic para um servidor falso. Vazio = API real.
    anthropic_base_url: str = ""
    # Opcional: IDs de contas (separados por vírgula) que esta instalação pode ler pelo Windsor.ai.
    # Vazio = todas as contas da chave. Útil quando a chave enxerga contas fora do escopo de trabalho.
    windsor_allowed_accounts: str = ""

    def allowed_accounts(self) -> set[str] | None:
        ids = {a.strip() for a in self.windsor_allowed_accounts.split(",") if a.strip()}
        return ids or None
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
