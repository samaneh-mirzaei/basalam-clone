from fastapi import APIRouter

from app.api.http import ContractRoute
from app.api.endpoints.v1.categories.router import router as categories_router
from app.api.endpoints.v1.products.router import router as products_router
from app.api.endpoints.v1.shops.router import router as shops_router
from app.api.endpoints.v1.users.router import router as users_router
from app.api.endpoints.v1.addresses.router import router as addresses_router
from app.api.endpoints.v1.wallets.router import router as wallets_router
from app.api.endpoints.v1.cart.router import router as cart_router
from app.api.endpoints.v1.orders.router import router as orders_router
from app.api.endpoints.v1.users.admin import router as admin_router

router = APIRouter(prefix="/api/v1", route_class=ContractRoute)
router.include_router(users_router)
router.include_router(admin_router)
router.include_router(addresses_router)
router.include_router(wallets_router)
router.include_router(cart_router)
router.include_router(orders_router)
router.include_router(shops_router)
router.include_router(categories_router)
router.include_router(products_router)
