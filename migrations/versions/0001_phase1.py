"""Phase 1 onboarding and catalog tables."""

from alembic import op
import sqlalchemy as sa

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("mobile", sa.String(11), nullable=False, unique=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mobile ~ '^09[0-9]{9}$'", name="ck_users_mobile"),
        sa.CheckConstraint("role IN ('customer', 'operator')", name="ck_users_role"))
    op.create_table("wallets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("balance >= 0", name="ck_wallet_balance"))
    op.create_table("wallet_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("wallet_id", sa.BigInteger(), sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("reference_id", sa.BigInteger()),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount <> 0 AND balance_after >= 0", name="ck_wtx_nonzero"),
        sa.CheckConstraint("(reason = 'order_payment' AND amount < 0) OR (reason IN ('order_refund', 'sale_settlement', 'initial_credit') AND amount > 0) OR reason = 'adjustment'", name="ck_wtx_sign_by_reason"),
        sa.CheckConstraint("reason IN ('initial_credit', 'adjustment') OR reference_id IS NOT NULL", name="ck_wtx_reference_required"),
        sa.CheckConstraint("reason <> 'adjustment' OR (note IS NOT NULL AND length(btrim(note)) > 0)", name="ck_wtx_adjustment_note"),
        sa.UniqueConstraint("wallet_id", "reason", "reference_id", name="uq_wallet_txn_idempotency"))
    op.create_index("uq_wtx_one_initial_credit", "wallet_transactions", ["wallet_id"], unique=True, postgresql_where=sa.text("reason = 'initial_credit'"))
    op.create_table("carts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("shops",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("shipping_fee", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("shipping_fee >= 0", name="ck_shop_ship_fee"),
        sa.CheckConstraint("status IN ('active', 'closed', 'suspended')", name="ck_shop_status"))
    op.create_table("categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="RESTRICT")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True))
    op.create_table("products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price >= 0", name="ck_product_price"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_product_stock"),
        sa.CheckConstraint("status IN ('draft', 'published', 'hidden', 'archived')", name="ck_product_status"),
        sa.UniqueConstraint("id", "shop_id", name="uq_product_id_shop"))
    op.create_index("ix_products_shop_status", "products", ["shop_id", "status"])
    op.create_table("product_images",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("product_id", "sort_order", name="uq_product_image_order"))


def downgrade():
    for table in ("product_images", "products", "categories", "shops", "carts", "wallet_transactions", "wallets", "users"):
        op.drop_table(table)
