"""Casos de uso (application service). Cada caso de uso = UMA transação que grava
o estado do agregado e os eventos de integração na outbox (ADR-0002)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from edp_events import SchemaValidator, add_to_outbox
from sqlalchemy.orm import Session

from pedidos.domain import CanceladoPor, InvarianteViolada, Item, MotivoCancelamento, Pedido
from pedidos.integration import to_integration_event
from pedidos.persistence import PedidoRepository, outbox_table


class PedidoNaoEncontrado(Exception):
    pass


class PedidosService:
    def __init__(self, session_factory: Callable[[], Session], validator: SchemaValidator, source: str):
        self._session_factory = session_factory
        self._validator = validator
        self._source = source

    def _persistir(self, session: Session, pedido: Pedido, versao_anterior: int | None, traceparent: str | None):
        PedidoRepository(session).salvar(pedido, versao_anterior, datetime.now(UTC))
        for domain_event in pedido.puxar_eventos():
            add_to_outbox(session, outbox_table, to_integration_event(domain_event, self._source, traceparent),
                          self._validator)

    def criar(self, cliente_id: str, itens: list[Item], moeda: str, traceparent: str | None = None) -> Pedido:
        pedido = Pedido.criar(cliente_id, itens, moeda)
        with self._session_factory() as session, session.begin():
            self._persistir(session, pedido, None, traceparent)
        return pedido

    def obter(self, pedido_id: str) -> Pedido:
        with self._session_factory() as session:
            pedido = PedidoRepository(session).obter(pedido_id)
        if pedido is None:
            raise PedidoNaoEncontrado(pedido_id)
        return pedido

    def _alterar(self, pedido_id: str, acao: Callable[[Pedido], None], traceparent: str | None) -> Pedido:
        with self._session_factory() as session, session.begin():
            pedido = PedidoRepository(session).obter(pedido_id, for_update=True)
            if pedido is None:
                raise PedidoNaoEncontrado(pedido_id)
            versao_anterior = pedido.versao
            acao(pedido)
            if pedido.versao != versao_anterior:  # operação idempotente não grava nada
                self._persistir(session, pedido, versao_anterior, traceparent)
        return pedido

    def confirmar(self, pedido_id: str, traceparent: str | None = None) -> Pedido:
        return self._alterar(pedido_id, lambda p: p.confirmar(), traceparent)

    def cancelar(self, pedido_id: str, motivo: MotivoCancelamento, cancelado_por: CanceladoPor,
                 traceparent: str | None = None) -> Pedido:
        return self._alterar(pedido_id, lambda p: p.cancelar(motivo, cancelado_por), traceparent)


__all__ = ["InvarianteViolada", "PedidoNaoEncontrado", "PedidosService"]
