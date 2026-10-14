# pedidos-service

**Bounded Context Pedidos.** API transacional em FastAPI que publica os eventos de integração do agregado `Pedido` via **Transactional Outbox**. É o domínio de referência que prova a plataforma de dados event-driven.

## Arquitetura (DDD)

```
src/pedidos/
  domain.py        # Agregado Pedido + domain events. Puro: sem framework, banco ou broker
  integration.py   # Published Language: domain event -> CloudEvent (contrato público)
  service.py       # Casos de uso: 1 transação = estado do agregado + eventos na outbox
  persistence.py   # Tabela pedido (concorrência otimista por versão) + outbox (platform-event-sdk)
  api.py           # FastAPI (HTTP <-> casos de uso)
  relay.py         # Worker: outbox -> Event Hubs (Deployment separado)
  migrations/      # Alembic
contracts/
  pedidos.pedido.v1.odcs.yaml          # contrato ODCS (fonte única, ADR-0005)
  schemas/*.schema.json                # GERADOS: edp-contracts generate contracts/pedidos.pedido.v1.odcs.yaml --out contracts/schemas
```

| Evento de integração | Quando | Versão do agregado |
|---|---|---|
| `pedidos.pedido.criado.v1` | `POST /pedidos` | 1 |
| `pedidos.pedido.confirmado.v1` | `POST /pedidos/{id}/confirmacao`, que na Fase 5 vira policy sobre `PagamentoAprovado` | +1 |
| `pedidos.pedido.cancelado.v1` | `POST /pedidos/{id}/cancelamento` | +1 |

Todos são publicados no event hub `pedidos.pedido.v1`, com `partition_key = pedido_id` (ADR-0008).

## API

```bash
curl -X POST localhost:8000/pedidos -H 'content-type: application/json' -d '{
  "cliente_id": "cli-000123",
  "itens": [{"sku": "LIVRO-DDD-001", "quantidade": 1, "preco_unitario": "189.90"}]
}'
```

| Código | Significado |
|---|---|
| 404 | Pedido inexistente |
| 409 | Invariante violada (ex.: confirmar um pedido cancelado) ou conflito de versão |
| 422 | Payload inválido |

## Execução

| Modo | Banco | Eventos |
|---|---|---|
| Local / testes | `DATABASE_URL=sqlite:///pedidos.db` | Ficam na outbox (sem relay) |
| AKS (Azure) | Postgres Flexible via **Entra ID**: o token da Workload Identity é a senha | Relay publica no Event Hubs com Entra ID |

Variáveis de ambiente, injetadas pelo `platform-gitops`:

| Variável | Uso |
|---|---|
| `POSTGRES_HOST` | Host do Postgres |
| `POSTGRES_DB` | Database (padrão `pedidos`) |
| `POSTGRES_USER` | Nome da managed identity |
| `OUTBOX_RELAY_ROLE` | Role Entra do relay, que recebe `GRANT` na outbox |
| `EVENTHUB_NAMESPACE_FQDN` | Namespace do Event Hubs (só o relay) |

```bash
pip install -e ".[dev]"
ruff check . && pytest
DATABASE_URL=sqlite:///pedidos.db uvicorn pedidos.api:app --reload
```

## CI/CD

Pipeline `.github/workflows/service.yml`, que usa o [`platform-cicd-workflows@v1`](https://github.com/ViniciusOtoni/platform-cicd-workflows):

| Evento | O que roda |
|---|---|
| PR | `ci-contracts` (lint ODCS v3.2.0, schemas gerados em dia, **bloqueio de breaking changes**) + `ci-python` (ruff + pytest) + `ci-container` (build + Trivy) |
| Merge na `main` | Push `sha-xxxxxxx` no ACR + `cd-gitops-promote`, que faz commit no `platform-gitops`; o Flux então aplica no AKS |

## ADRs relacionados

0002 (Outbox), 0003 (CloudEvents + JSON Schema), 0005 (ODCS), 0008 (event hub por agregado) e 0011 (FastAPI + Postgres).
