import pytest
from fastapi.testclient import TestClient

from pedidos.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Banco local (sqlite) com as migrações reais do Alembic.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pedidos.db'}")
    monkeypatch.setenv("RUN_MIGRATIONS", "true")
    get_settings.cache_clear()
    from pedidos.api import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
