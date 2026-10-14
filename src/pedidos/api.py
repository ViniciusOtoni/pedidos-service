"""API HTTP do BC Pedidos (FastAPI)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated

from alembic import command
from alembic.config import Config
from edp_events import SchemaValidator
from fastapi import Depends, FastAPI, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from pedidos.config import get_settings
from pedidos.db import create_db_engine, session_factory
from pedidos.domain import CanceladoPor, InvarianteViolada, Item, MotivoCancelamento, Pedido
from pedidos.persistence import ConflitoDeVersao, metadata
from pedidos.service import PedidoNaoEncontrado, PedidosService


def run_migrations(engine) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "pedidos:migrations")
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = create_db_engine(settings)
    if settings.run_migrations:
        run_migrations(engine)
    else:
        metadata.create_all(engine)
    app.state.engine = engine
    app.state.service = PedidosService(
        session_factory(engine), SchemaValidator.from_directory(settings.contracts_dir), settings.event_source
    )
    yield
    engine.dispose()


app = FastAPI(title="pedidos-service", version="0.1.0", lifespan=lifespan)


def get_service(request: Request) -> PedidosService:
    return request.app.state.service


Service = Annotated[PedidosService, Depends(get_service)]
TraceParent = Annotated[str | None, Header()]


# ------------------------------------------------------------------ DTOs
class ItemIn(BaseModel):
    sku: str = Field(min_length=1)
    quantidade: int = Field(ge=1)
    preco_unitario: Decimal = Field(ge=0)


class CriarPedidoIn(BaseModel):
    cliente_id: str = Field(min_length=1)
    itens: list[ItemIn] = Field(min_length=1)
    moeda: str = "BRL"


class CancelarPedidoIn(BaseModel):
    motivo: MotivoCancelamento = MotivoCancelamento.CLIENTE_DESISTIU


class PedidoOut(BaseModel):
    pedido_id: str
    cliente_id: str
    itens: list[ItemIn]
    valor_total: Decimal
    moeda: str
    status: str
    versao: int

    @classmethod
    def de(cls, p: Pedido) -> PedidoOut:
        return cls(
            pedido_id=p.pedido_id, cliente_id=p.cliente_id, moeda=p.moeda, status=p.status.value, versao=p.versao,
            valor_total=p.valor_total,
            itens=[ItemIn(sku=i.sku, quantidade=i.quantidade, preco_unitario=i.preco_unitario) for i in p.itens],
        )


# ------------------------------------------------------------------ erros de domínio -> HTTP
@app.exception_handler(PedidoNaoEncontrado)
async def _nao_encontrado(_, exc):
    return JSONResponse({"detail": f"Pedido {exc} não encontrado"}, status.HTTP_404_NOT_FOUND)


@app.exception_handler(InvarianteViolada)
async def _invariante(_, exc):
    return JSONResponse({"detail": str(exc)}, status.HTTP_409_CONFLICT)


@app.exception_handler(ConflitoDeVersao)
async def _conflito(_, exc):
    return JSONResponse({"detail": f"Pedido {exc} alterado concorrentemente; tente novamente"},
                        status.HTTP_409_CONFLICT)


# ------------------------------------------------------------------ endpoints
@app.post("/pedidos", status_code=status.HTTP_201_CREATED, response_model=PedidoOut)
def criar_pedido(body: CriarPedidoIn, service: Service, traceparent: TraceParent = None):
    itens = [Item(i.sku, i.quantidade, i.preco_unitario) for i in body.itens]
    return PedidoOut.de(service.criar(body.cliente_id, itens, body.moeda, traceparent))


@app.get("/pedidos/{pedido_id}", response_model=PedidoOut)
def obter_pedido(pedido_id: str, service: Service):
    return PedidoOut.de(service.obter(pedido_id))


# Temporário: na Fase 5 a confirmação vem da policy "ao aprovar pagamento, confirmar pedido".
@app.post("/pedidos/{pedido_id}/confirmacao", response_model=PedidoOut)
def confirmar_pedido(pedido_id: str, service: Service, traceparent: TraceParent = None):
    return PedidoOut.de(service.confirmar(pedido_id, traceparent))


@app.post("/pedidos/{pedido_id}/cancelamento", response_model=PedidoOut)
def cancelar_pedido(pedido_id: str, body: CancelarPedidoIn, service: Service, traceparent: TraceParent = None):
    return PedidoOut.de(service.cancelar(pedido_id, body.motivo, CanceladoPor.CLIENTE, traceparent))


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(request: Request):
    with request.app.state.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
