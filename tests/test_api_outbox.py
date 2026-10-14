import json

from edp_events import OutboxRelay
from edp_events.publishers import InMemoryPublisher
from sqlalchemy import select

from pedidos.persistence import outbox_table

NOVO_PEDIDO = {
    "cliente_id": "cli-000123",
    "itens": [
        {"sku": "LIVRO-DDD-001", "quantidade": 1, "preco_unitario": "189.90"},
        {"sku": "CANECA-KAFKA", "quantidade": 2, "preco_unitario": "39.50"},
    ],
}


def _outbox(client):
    with client.app.state.engine.connect() as conn:
        return conn.execute(select(outbox_table).order_by(outbox_table.c.created_at)).mappings().all()


def test_criar_pedido_grava_estado_e_evento_na_outbox(client):
    r = client.post("/pedidos", json=NOVO_PEDIDO, headers={"traceparent": "00-abc-def-01"})
    assert r.status_code == 201, r.text
    pedido = r.json()
    assert pedido["valor_total"] == "268.90" and pedido["versao"] == 1

    assert client.get(f"/pedidos/{pedido['pedido_id']}").json()["status"] == "CRIADO"

    [row] = _outbox(client)
    assert row["event_type"] == "pedidos.pedido.criado.v1"
    assert row["event_hub"] == "pedidos.pedido.v1"
    assert row["aggregate_id"] == pedido["pedido_id"]
    assert row["payload"]["data"]["valor_total"] == 268.9
    assert row["payload"]["traceparent"] == "00-abc-def-01"


def test_ciclo_de_vida_gera_eventos_versionados(client):
    pid = client.post("/pedidos", json=NOVO_PEDIDO).json()["pedido_id"]
    assert client.post(f"/pedidos/{pid}/confirmacao").json()["versao"] == 2
    assert client.post(f"/pedidos/{pid}/confirmacao").json()["versao"] == 2  # idempotente
    r = client.post(f"/pedidos/{pid}/cancelamento", json={"motivo": "CLIENTE_DESISTIU"})
    assert r.json()["status"] == "CANCELADO"

    rows = _outbox(client)
    assert [(x["event_type"], x["aggregate_version"]) for x in rows] == [
        ("pedidos.pedido.criado.v1", 1),
        ("pedidos.pedido.confirmado.v1", 2),
        ("pedidos.pedido.cancelado.v1", 3),
    ]


def test_invariante_vira_409_e_nada_vai_para_outbox(client):
    pid = client.post("/pedidos", json=NOVO_PEDIDO).json()["pedido_id"]
    client.post(f"/pedidos/{pid}/cancelamento", json={})
    r = client.post(f"/pedidos/{pid}/confirmacao")
    assert r.status_code == 409
    assert len(_outbox(client)) == 2


def test_validacoes_http(client):
    assert client.post("/pedidos", json={"cliente_id": "x", "itens": []}).status_code == 422
    assert client.get("/pedidos/inexistente").status_code == 404
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_relay_publica_cloudevents_na_ordem_com_chave_do_agregado(client):
    pid = client.post("/pedidos", json=NOVO_PEDIDO).json()["pedido_id"]
    client.post(f"/pedidos/{pid}/confirmacao")

    publisher = InMemoryPublisher()
    from sqlalchemy.orm import sessionmaker

    relay = OutboxRelay(sessionmaker(client.app.state.engine), outbox_table, publisher)
    assert relay.run_once() == 2
    assert {m.partition_key for m in publisher.messages} == {pid}
    tipos = [json.loads(m.body)["type"] for m in publisher.messages]
    assert tipos == ["pedidos.pedido.criado.v1", "pedidos.pedido.confirmado.v1"]
