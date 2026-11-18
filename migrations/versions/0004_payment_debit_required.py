"""Require every wallet payment to reference its ledger debit."""

from alembic import op
import sqlalchemy as sa

revision = "0004_payment_debit_required"
down_revision = "0003_address_phone_length"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("payments", "wallet_transaction_id", existing_type=sa.BigInteger(), nullable=False)


def downgrade():
    op.alter_column("payments", "wallet_transaction_id", existing_type=sa.BigInteger(), nullable=True)
