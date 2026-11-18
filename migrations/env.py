from alembic import context

from app.core.config import settings
from app.data.base import Base
from app.data.session import engine
from app.schemas.users import models as users_models
from app.schemas.shops import models as shops_models
from app.schemas.categories import models as categories_models
from app.schemas.products import models as products_models
from app.schemas.addresses import models as addresses_models
from app.schemas.cart import models as cart_models
from app.schemas.orders import models as orders_models
from app.schemas.parcels import models as parcels_models
from app.schemas.returns import models as returns_models
from app.schemas.refunds import models as refunds_models


def include_name(name, type_, parent_names):
    return type_ != "table" or name in Base.metadata.tables or name == "alembic_version"


if context.is_offline_mode():
    context.configure(url=settings().database_url.get_secret_value(), target_metadata=Base.metadata, literal_binds=True, include_name=include_name)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()
