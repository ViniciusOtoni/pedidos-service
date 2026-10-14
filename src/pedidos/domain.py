"""Modelo de domínio do BC Pedidos (DDD). Puro: sem framework, sem banco, sem broker.

O agregado ``Pedido`` protege as invariantes e registra **domain events**. A tradução para eventos de
integração (Published Language) acontece fora daqui, em ``integration.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class InvarianteViolada(Exception):
    """Regra de negócio do agregado foi violada (HTTP 409)."""


class StatusPedido(StrEnum):
    CRIADO = "CRIADO"
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"


class MotivoCancelamento(StrEnum):
    CLIENTE_DESISTIU = "CLIENTE_DESISTIU"
    PAGAMENTO_RECUSADO = "PAGAMENTO_RECUSADO"
    FRAUDE = "FRAUDE"


class CanceladoPor(StrEnum):
    CLIENTE = "CLIENTE"
    SISTEMA = "SISTEMA"


@dataclass(frozen=True)
class Item:
    sku: str
    quantidade: int
    preco_unitario: Decimal

    def __post_init__(self) -> None:
        if not self.sku:
            raise InvarianteViolada("sku é obrigatório")
        if self.quantidade < 1:
            raise InvarianteViolada("quantidade deve ser >= 1")
        if self.preco_unitario < 0:
            raise InvarianteViolada("preco_unitario não pode ser negativo")

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade


# ------------------------------------------------------------------ domain events
@dataclass(frozen=True)
class PedidoCriado:
    pedido: Pedido


@dataclass(frozen=True)
class PedidoConfirmado:
    pedido: Pedido
    confirmado_em: datetime


@dataclass(frozen=True)
class PedidoCancelado:
    pedido: Pedido
    motivo: MotivoCancelamento
    cancelado_por: CanceladoPor
    cancelado_em: datetime


DomainEvent = PedidoCriado | PedidoConfirmado | PedidoCancelado


# ------------------------------------------------------------------ aggregate
@dataclass
class Pedido:
    pedido_id: str
    cliente_id: str
    itens: tuple[Item, ...]
    moeda: str
    status: StatusPedido
    versao: int
    criado_em: datetime
    _eventos: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    @property
    def valor_total(self) -> Decimal:
        return sum((i.subtotal for i in self.itens), Decimal("0"))

    @classmethod
    def criar(cls, cliente_id: str, itens: list[Item], moeda: str = "BRL") -> Pedido:
        if not cliente_id:
            raise InvarianteViolada("cliente_id é obrigatório")
        if not itens:
            raise InvarianteViolada("pedido precisa de ao menos um item")
        if len(moeda) != 3 or not moeda.isupper():
            raise InvarianteViolada("moeda deve ser ISO 4217 (ex.: BRL)")
        pedido = cls(
            pedido_id=str(uuid.uuid4()),
            cliente_id=cliente_id,
            itens=tuple(itens),
            moeda=moeda,
            status=StatusPedido.CRIADO,
            versao=1,
            criado_em=datetime.now(UTC),
        )
        if pedido.valor_total <= 0:
            raise InvarianteViolada("valor_total deve ser positivo")
        pedido._eventos.append(PedidoCriado(pedido))
        return pedido

    def confirmar(self) -> None:
        if self.status is StatusPedido.CONFIRMADO:
            return  # idempotente: reprocessar PagamentoAprovado não gera novo evento
        if self.status is StatusPedido.CANCELADO:
            raise InvarianteViolada("pedido cancelado não pode ser confirmado")
        self.status = StatusPedido.CONFIRMADO
        self.versao += 1
        self._eventos.append(PedidoConfirmado(self, datetime.now(UTC)))

    def cancelar(self, motivo: MotivoCancelamento, cancelado_por: CanceladoPor) -> None:
        if self.status is StatusPedido.CANCELADO:
            return  # idempotente
        self.status = StatusPedido.CANCELADO
        self.versao += 1
        self._eventos.append(PedidoCancelado(self, motivo, cancelado_por, datetime.now(UTC)))

    def puxar_eventos(self) -> list[DomainEvent]:
        eventos, self._eventos = self._eventos, []
        return eventos
