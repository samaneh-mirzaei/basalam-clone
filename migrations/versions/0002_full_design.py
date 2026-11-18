"""Complete the supplied DBML schema and companion constraints."""

from alembic import op

revision = "0002_full_design"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None


def upgrade():
    for statement in (
        "CREATE TYPE user_role AS ENUM ('customer', 'operator')",
        "CREATE TYPE shop_status AS ENUM ('active', 'suspended', 'closed')",
        "CREATE TYPE product_status AS ENUM ('draft', 'published', 'hidden', 'archived')",
        "CREATE TYPE order_status AS ENUM ('paid', 'cancelled')",
        "CREATE TYPE parcel_status AS ENUM ('pending', 'preparing', 'shipped', 'delivered', 'cancelled')",
        "CREATE TYPE payment_method AS ENUM ('wallet')",
        "CREATE TYPE refund_reason AS ENUM ('parcel_cancelled', 'return_accepted', 'goodwill')",
        "CREATE TYPE wallet_txn_reason AS ENUM ('initial_credit', 'order_payment', 'order_refund', 'sale_settlement', 'adjustment')",
        "CREATE TYPE return_status AS ENUM ('requested', 'approved', 'rejected')",
        "ALTER TABLE users ALTER COLUMN role DROP DEFAULT",
        "ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role",
        "ALTER TABLE users ALTER COLUMN role SET DEFAULT 'customer'::user_role",
        "ALTER TABLE shops ALTER COLUMN status DROP DEFAULT",
        "ALTER TABLE shops ALTER COLUMN status TYPE shop_status USING status::shop_status",
        "ALTER TABLE shops ALTER COLUMN status SET DEFAULT 'active'::shop_status",
        "ALTER TABLE products ALTER COLUMN status DROP DEFAULT",
        "ALTER TABLE products ALTER COLUMN status TYPE product_status USING status::product_status",
        "ALTER TABLE products ALTER COLUMN status SET DEFAULT 'draft'::product_status",
        "DROP INDEX uq_wtx_one_initial_credit",
        "ALTER TABLE wallet_transactions ALTER COLUMN reason TYPE wallet_txn_reason USING reason::wallet_txn_reason",
        "CREATE UNIQUE INDEX uq_wtx_one_initial_credit ON wallet_transactions (wallet_id) WHERE reason = 'initial_credit'",
        "ALTER TABLE product_images ALTER COLUMN sort_order TYPE smallint",
        "CREATE INDEX ix_wallet_transactions_wallet_created ON wallet_transactions (wallet_id, created_at)",
        "CREATE INDEX ix_products_category_id ON products (category_id)",
        """CREATE TABLE user_addresses (
            id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient_name varchar(100) NOT NULL, recipient_phone varchar(15) NOT NULL,
            province varchar(50) NOT NULL, city varchar(50) NOT NULL,
            address_line varchar(300) NOT NULL, postal_code varchar(10) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now())""",
        "CREATE INDEX ix_user_addresses_user_id ON user_addresses (user_id)",
        """CREATE TABLE cart_items (
            id bigserial PRIMARY KEY, cart_id bigint NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
            product_id bigint NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            quantity int NOT NULL DEFAULT 1, added_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_cart_items_cart_product UNIQUE (cart_id, product_id),
            CONSTRAINT ck_cart_qty CHECK (quantity > 0))""",
        """CREATE TABLE saved_items (
            id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id bigint NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            saved_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_saved_items_user_product UNIQUE (user_id, product_id))""",
        """CREATE TABLE orders (
            id bigserial PRIMARY KEY, customer_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            checkout_key varchar(64) NOT NULL, request_hash varchar(64) NOT NULL,
            status order_status NOT NULL DEFAULT 'paid', total_amount bigint NOT NULL,
            ship_recipient_name varchar(100) NOT NULL, ship_recipient_phone varchar(15) NOT NULL,
            ship_province varchar(50) NOT NULL, ship_city varchar(50) NOT NULL,
            ship_address_line varchar(300) NOT NULL, ship_postal_code varchar(10) NOT NULL,
            placed_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            cancelled_at timestamptz,
            CONSTRAINT uq_order_checkout_key UNIQUE (customer_id, checkout_key),
            CONSTRAINT ck_order_total CHECK (total_amount > 0),
            CONSTRAINT ck_order_cancel_consistent CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL)),
            CONSTRAINT ck_order_request_hash CHECK (request_hash ~ '^[0-9a-f]{64}$'))""",
        "CREATE INDEX ix_orders_customer_placed ON orders (customer_id, placed_at)",
        """CREATE TABLE order_parcels (
            id bigserial PRIMARY KEY, order_id bigint NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
            shop_id bigint NOT NULL REFERENCES shops(id) ON DELETE RESTRICT,
            shipping_fee bigint NOT NULL DEFAULT 0, status parcel_status NOT NULL DEFAULT 'pending',
            tracking_code varchar(50), created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), shipped_at timestamptz,
            delivered_at timestamptz, cancelled_at timestamptz, settled_at timestamptz,
            CONSTRAINT uq_order_parcel_shop UNIQUE (order_id, shop_id),
            CONSTRAINT uq_parcel_id_shop UNIQUE (id, shop_id),
            CONSTRAINT ck_parcel_ship_fee CHECK (shipping_fee >= 0),
            CONSTRAINT ck_parcel_cancel_consistent CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL)),
            CONSTRAINT ck_parcel_settle_after_delivery CHECK (settled_at IS NULL OR status = 'delivered'))""",
        "CREATE INDEX ix_parcels_shop_status ON order_parcels (shop_id, status)",
        """CREATE TABLE order_items (
            id bigserial PRIMARY KEY, parcel_id bigint NOT NULL, shop_id bigint NOT NULL,
            product_id bigint NOT NULL, product_title varchar(200) NOT NULL,
            unit_price bigint NOT NULL, quantity int NOT NULL,
            CONSTRAINT uq_order_item_product UNIQUE (parcel_id, product_id),
            CONSTRAINT fk_order_item_parcel_shop FOREIGN KEY (parcel_id, shop_id)
                REFERENCES order_parcels(id, shop_id) ON DELETE RESTRICT,
            CONSTRAINT fk_order_item_product_shop FOREIGN KEY (product_id, shop_id)
                REFERENCES products(id, shop_id) ON DELETE RESTRICT,
            CONSTRAINT ck_item_qty CHECK (quantity > 0),
            CONSTRAINT ck_item_price CHECK (unit_price >= 0))""",
        "CREATE INDEX ix_order_items_product_id ON order_items (product_id)",
        """CREATE TABLE payments (
            id bigserial PRIMARY KEY, order_id bigint NOT NULL UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
            wallet_transaction_id bigint UNIQUE REFERENCES wallet_transactions(id) ON DELETE RESTRICT,
            method payment_method NOT NULL DEFAULT 'wallet', amount bigint NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_payment_amount CHECK (amount > 0))""",
        """CREATE TABLE return_requests (
            id bigserial PRIMARY KEY, parcel_id bigint NOT NULL UNIQUE REFERENCES order_parcels(id) ON DELETE RESTRICT,
            reason_text varchar(500) NOT NULL, status return_status NOT NULL DEFAULT 'requested',
            response_note varchar(500), created_at timestamptz NOT NULL DEFAULT now(), decided_at timestamptz,
            CONSTRAINT ck_return_decision_consistent CHECK ((status = 'requested') = (decided_at IS NULL)),
            CONSTRAINT ck_return_rejection_note CHECK (status <> 'rejected' OR response_note IS NOT NULL))""",
        """CREATE TABLE refunds (
            id bigserial PRIMARY KEY, parcel_id bigint NOT NULL REFERENCES order_parcels(id) ON DELETE RESTRICT,
            amount bigint NOT NULL, reason refund_reason NOT NULL,
            return_request_id bigint UNIQUE REFERENCES return_requests(id) ON DELETE RESTRICT,
            wallet_transaction_id bigint NOT NULL UNIQUE REFERENCES wallet_transactions(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_refund_amount CHECK (amount > 0),
            CONSTRAINT ck_refund_return_link CHECK ((reason = 'return_accepted') = (return_request_id IS NOT NULL)))""",
        "CREATE INDEX ix_refunds_parcel_id ON refunds (parcel_id)",
    ):
        op.execute(statement)


def downgrade():
    for table in ("refunds", "return_requests", "payments", "order_items", "order_parcels", "orders", "saved_items", "cart_items", "user_addresses"):
        op.drop_table(table)
    op.execute("DROP INDEX ix_products_category_id")
    op.execute("DROP INDEX ix_wallet_transactions_wallet_created")
    op.execute("ALTER TABLE product_images ALTER COLUMN sort_order TYPE integer")
    op.execute("DROP INDEX uq_wtx_one_initial_credit")
    for table, column, length, default in (
        ("users", "role", 20, "customer"),
        ("shops", "status", 20, "active"),
        ("products", "status", 20, "draft"),
        ("wallet_transactions", "reason", 30, None),
    ):
        if default:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar({length}) USING {column}::text")
        if default:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
    op.execute("CREATE UNIQUE INDEX uq_wtx_one_initial_credit ON wallet_transactions (wallet_id) WHERE reason = 'initial_credit'")
    for enum in ("return_status", "wallet_txn_reason", "refund_reason", "payment_method", "parcel_status", "order_status", "product_status", "shop_status", "user_role"):
        op.execute(f"DROP TYPE {enum}")
