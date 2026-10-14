from decimal import Decimal

import pytest

from pedidos.domain import (
    CanceladoPor,
    InvarianteViolada,
    Item,
    MotivoCancelamento,
    Pedido,
    PedidoCancelado,
    PedidoConfirmado,
    PedidoCriado,
    StatusPedido,
)


def _pedido() -> Pedido:
    return Pedido.criar("cli-1", [Item("LIVRO", 1, Decimal("189.90")), Item("CANECA", 2, Decimal("39.50"))])


def test_criar_calcula_total_e_registra_evento():
    p = _pedido()
    assert p.valor_total == Decimal("268.90")
    assert (p.status, p.versao) == (StatusPedido.CRIADO, 1)
    assert [type(e) for e in p.puxar_eventos()] == [PedidoCriado]
    assert p.puxar_eventos() == []


@pytest.mark.parametrize(
    "itens",
    [[], [Item("A", 1, Decimal("0"))]],
)
def test_criar_rejeita_pedido_vazio_ou_sem_valor(itens):
    with pytest.raises(InvarianteViolada):
        Pedido.criar("cli-1", itens)


def test_item_invalido():
    with pytest.raises(InvarianteViolada):
        Item("A", 0, Decimal("1"))


def test_confirmar_incrementa_versao_e_e_idempotente():
    p = _pedido()
    p.puxar_eventos()
    p.confirmar()
    p.confirmar()
    assert (p.status, p.versao) == (StatusPedido.CONFIRMADO, 2)
    assert [type(e) for e in p.puxar_eventos()] == [PedidoConfirmado]


def test_cancelado_nao_pode_ser_confirmado():
    p = _pedido()
    p.cancelar(MotivoCancelamento.CLIENTE_DESISTIU, CanceladoPor.CLIENTE)
    with pytest.raises(InvarianteViolada):
        p.confirmar()


def test_cancelar_pedido_confirmado():
    p = _pedido()
    p.confirmar()
    p.cancelar(MotivoCancelamento.FRAUDE, CanceladoPor.SISTEMA)
    p.cancelar(MotivoCancelamento.FRAUDE, CanceladoPor.SISTEMA)
    assert (p.status, p.versao) == (StatusPedido.CANCELADO, 3)
    assert [type(e) for e in p.puxar_eventos()] == [PedidoCriado, PedidoConfirmado, PedidoCancelado]
