from app.handlers.admin_panel import router as admin_router
from app.handlers.token import router as token_router
from app.handlers.user_catalog import router as user_catalog_router


# Order matters:
# - token_router first, so deep-link /start TOKEN is handled before the plain /start.
# - admin_router before user_catalog_router, so admin FSM state messages take priority.
routers = (
    token_router,
    admin_router,
    user_catalog_router,
)
