"""Configuração via variáveis de ambiente (injetadas pelo platform-gitops / Flux postBuild)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "schemas"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Banco. DATABASE_URL (ex.: sqlite) tem precedência: uso local e testes.
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_db: str = "pedidos"
    postgres_user: str | None = None  # nome da managed identity (usuário Entra no Postgres)
    run_migrations: bool = True
    outbox_relay_role: str | None = None  # role do relay que recebe GRANT na tabela outbox

    # Eventos
    event_source: str = "/dominios/pedidos/pedidos-api"
    contracts_dir: Path = _DEFAULT_CONTRACTS
    eventhub_namespace_fqdn: str | None = None
    relay_batch_size: int = 100
    relay_poll_interval_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
