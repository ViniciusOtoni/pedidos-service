"""cria tabelas pedido e outbox

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

from pedidos.config import get_settings
from pedidos.persistence import outbox_table

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pedido",
        sa.Column("pedido_id", sa.String(36), primary_key=True),
        sa.Column("cliente_id", sa.String(100), nullable=False),
        sa.Column("itens", sa.JSON, nullable=False),
        sa.Column("valor_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("moeda", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    # A estrutura da outbox pertence ao platform-event-sdk (versão fixada no pyproject).
    outbox_table.create(bind=op.get_bind())

    # O relay roda com outra identidade (role Entra própria): precisa ler/marcar a outbox.
    relay_role = get_settings().outbox_relay_role
    if relay_role and op.get_bind().dialect.name == "postgresql":
        op.execute(f'GRANT SELECT, UPDATE ON outbox TO "{relay_role}"')


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("pedido")
