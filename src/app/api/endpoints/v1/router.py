from fastapi import APIRouter

from app.api.http import ContractRoute
from app.api.endpoints.v1.categories.router import router as categories_router
from app.api.endpoints.v1.products.router import router as products_router
from app.api.endpoints.v1.shops.router import router as shops_router
from app.api.endpoints.v1.users.router import router as users_router

router = APIRouter(prefix="/api/v1", route_class=ContractRoute)
router.include_router(users_router)
router.include_router(shops_router)
router.include_router(categories_router)
router.include_router(products_router)
