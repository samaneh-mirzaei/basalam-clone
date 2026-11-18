"""Allow a leading plus and fifteen digits in address phone fields."""

from alembic import op
import sqlalchemy as sa

revision = "0003_address_phone_length"
down_revision = "0002_full_design"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("user_addresses", "recipient_phone", existing_type=sa.String(15), type_=sa.String(16), existing_nullable=False)
    op.alter_column("orders", "ship_recipient_phone", existing_type=sa.String(15), type_=sa.String(16), existing_nullable=False)


def downgrade():
    op.alter_column("orders", "ship_recipient_phone", existing_type=sa.String(16), type_=sa.String(15), existing_nullable=False)
    op.alter_column("user_addresses", "recipient_phone", existing_type=sa.String(16), type_=sa.String(15), existing_nullable=False)
