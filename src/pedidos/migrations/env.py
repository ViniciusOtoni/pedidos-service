"""Ambiente Alembic: usa a mesma engine da aplicação (Entra ID em Azure, DATABASE_URL localmente)."""

from alembic import context

from pedidos.config import get_settings
from pedidos.db import create_db_engine
from pedidos.persistence import metadata

connectable = context.config.attributes.get("connection")


def run() -> None:
    if connectable is not None:
        context.configure(connection=connectable, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_db_engine(get_settings())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
