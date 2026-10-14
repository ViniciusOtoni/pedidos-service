"""Persistência do agregado Pedido (tabela ``pedido``) e da outbox, com concorrência otimista."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from edp_events import register_outbox
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, Numeric, String, Table, select, update
from sqlalchemy.orm import Session

from pedidos.domain import Item, Pedido, StatusPedido

metadata = MetaData()

pedido_table = Table(
    "pedido",
    metadata,
    Column("pedido_id", String(36), primary_key=True),
    Column("cliente_id", String(100), nullable=False),
    Column("itens", JSON, nullable=False),
    Column("valor_total", Numeric(14, 2), nullable=False),
    Column("moeda", String(3), nullable=False),
    Column("status", String(20), nullable=False),
    Column("versao", Integer, nullable=False),
    Column("criado_em", DateTime(timezone=True), nullable=False),
    Column("atualizado_em", DateTime(timezone=True), nullable=False),
)

outbox_table = register_outbox(metadata)


class ConflitoDeVersao(Exception):
    """Outra transação alterou o pedido entre a leitura e a gravação (HTTP 409)."""


class PedidoRepository:
    def __init__(self, session: Session):
        self._session = session

    def obter(self, pedido_id: str, for_update: bool = False) -> Pedido | None:
        query = select(pedido_table).where(pedido_table.c.pedido_id == pedido_id)
        if for_update:
            query = query.with_for_update()
        row = self._session.execute(query).mappings().first()
        if row is None:
            return None
        return Pedido(
            pedido_id=row["pedido_id"],
            cliente_id=row["cliente_id"],
            itens=tuple(
                Item(i["sku"], int(i["quantidade"]), Decimal(str(i["preco_unitario"]))) for i in row["itens"]
            ),
            moeda=row["moeda"],
            status=StatusPedido(row["status"]),
            versao=row["versao"],
            criado_em=row["criado_em"],
        )

    def salvar(self, pedido: Pedido, versao_anterior: int | None, agora: datetime) -> None:
        values = {
            "cliente_id": pedido.cliente_id,
            "itens": [
                {"sku": i.sku, "quantidade": i.quantidade, "preco_unitario": str(i.preco_unitario)}
                for i in pedido.itens
            ],
            "valor_total": pedido.valor_total,
            "moeda": pedido.moeda,
            "status": pedido.status.value,
            "versao": pedido.versao,
            "atualizado_em": agora,
        }
        if versao_anterior is None:
            self._session.execute(
                pedido_table.insert().values(pedido_id=pedido.pedido_id, criado_em=pedido.criado_em, **values)
            )
            return
        result = self._session.execute(
            update(pedido_table)
            .where(pedido_table.c.pedido_id == pedido.pedido_id, pedido_table.c.versao == versao_anterior)
            .values(**values)
        )
        if result.rowcount != 1:
            raise ConflitoDeVersao(pedido.pedido_id)
