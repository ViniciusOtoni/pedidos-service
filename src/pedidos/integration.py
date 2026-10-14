"""Published Language do BC Pedidos: tradução domain event -> evento de integração (CloudEvent).

Esta é a fronteira explícita entre o modelo interno (livre para evoluir) e o contrato público
(``contracts/pedidos.pedido.v1.odcs.yaml``). Os payloads seguem Event-Carried State Transfer:
carregam o estado necessário para o consumidor não precisar chamar esta API.
"""

from __future__ import annotations

from edp_events import CloudEvent, new_event

from pedidos.domain import DomainEvent, PedidoCancelado, PedidoConfirmado, PedidoCriado

AGGREGATE = "pedido"


def _iso(dt) -> str:
    return dt.isoformat(timespec="milliseconds")


def to_integration_event(event: DomainEvent, source: str, traceparent: str | None = None) -> CloudEvent:
    pedido = event.pedido
    match event:
        case PedidoCriado():
            type_ = "pedidos.pedido.criado.v1"
            data = {
                "pedido_id": pedido.pedido_id,
                "aggregate_version": pedido.versao,
                "cliente_id": pedido.cliente_id,
                "itens": [
                    {"sku": i.sku, "quantidade": i.quantidade, "preco_unitario": float(i.preco_unitario)}
                    for i in pedido.itens
                ],
                "valor_total": float(pedido.valor_total),
                "moeda": pedido.moeda,
                "criado_em": _iso(pedido.criado_em),
            }
        case PedidoConfirmado():
            type_ = "pedidos.pedido.confirmado.v1"
            data = {
                "pedido_id": pedido.pedido_id,
                "aggregate_version": pedido.versao,
                "status": pedido.status.value,
                "confirmado_em": _iso(event.confirmado_em),
            }
        case PedidoCancelado():
            type_ = "pedidos.pedido.cancelado.v1"
            data = {
                "pedido_id": pedido.pedido_id,
                "aggregate_version": pedido.versao,
                "motivo": event.motivo.value,
                "cancelado_por": event.cancelado_por.value,
                "cancelado_em": _iso(event.cancelado_em),
            }
        case _:
            raise TypeError(f"Domain event sem mapeamento para a Published Language: {event!r}")

    return new_event(
        type=type_,
        source=source,
        aggregate=AGGREGATE,
        aggregate_id=pedido.pedido_id,
        aggregate_version=data["aggregate_version"],
        data=data,
        traceparent=traceparent,
    )
