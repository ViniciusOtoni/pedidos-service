"""Engine SQLAlchemy. Em Azure: Postgres Flexible com autenticação Entra ID (ADR-0011).

A "senha" é um token de acesso da managed identity da workload (Workload Identity), obtido a cada
nova conexão do pool. Nenhum segredo é configurado.
"""

from __future__ import annotations

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from pedidos.config import Settings

POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def create_db_engine(settings: Settings) -> Engine:
    if settings.database_url:
        return create_engine(settings.database_url)

    if not (settings.postgres_host and settings.postgres_user):
        raise RuntimeError("Defina DATABASE_URL ou POSTGRES_HOST + POSTGRES_USER")

    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    url = URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        host=settings.postgres_host,
        port=5432,
        database=settings.postgres_db,
    )
    # Tokens duram ~1h: recicla conexões antes disso.
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args={"sslmode": "require"})

    @event.listens_for(engine, "do_connect")
    def _entra_token(dialect, conn_rec, cargs, cparams):  # noqa: ARG001
        cparams["password"] = credential.get_token(POSTGRES_SCOPE).token

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
