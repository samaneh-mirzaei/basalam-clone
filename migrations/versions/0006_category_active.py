"""Retain referenced categories while allowing admins to deactivate them."""

from alembic import op
import sqlalchemy as sa

revision = "0006_category_active"
down_revision = "0005_admin_role"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade():
    op.drop_column("categories", "is_active")
