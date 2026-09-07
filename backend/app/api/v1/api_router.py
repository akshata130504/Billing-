from fastapi import APIRouter
from backend.app.api.v1.endpoints import health

api_router = APIRouter()

# Core system endpoints
api_router.include_router(health.router, tags=["Health"])

# Future Stage 1 routers will be included here:
# api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
# api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
# api_router.include_router(products.router, prefix="/products", tags=["Products"])
# api_router.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
# api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
# api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
# api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
