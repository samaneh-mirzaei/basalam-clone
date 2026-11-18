"""Add admin to the existing PostgreSQL user_role enum and role check."""

from alembic import op

revision = "0005_admin_role"
down_revision = "0004_payment_debit_required"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL cannot use a newly added enum label until its transaction commits.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'admin'")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('customer', 'operator', 'admin'))")


def downgrade():
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin')").scalar():
        raise RuntimeError("Demote admin users before downgrading this migration.")
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_role")
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TYPE user_role RENAME TO user_role_with_admin")
    op.execute("CREATE TYPE user_role AS ENUM ('customer', 'operator')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::text::user_role")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'customer'::user_role")
    op.execute("DROP TYPE user_role_with_admin")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('customer', 'operator'))")
