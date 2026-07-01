from app.handlers.admin_access import router as admin_access_router
from app.handlers.admin_panel import router as admin_router
from app.handlers.token import router as token_router
from app.handlers.user_catalog import router as user_catalog_router


# Order matters:
# - token_router first, so deep-link /start TOKEN is handled before the plain /start.
# - admin_router before user_catalog_router, so admin FSM state messages take priority.
# - admin_access_router carries owner-only commands (/grant, /revoke, /access).
routers = (
    token_router,
    admin_router,
    admin_access_router,
    user_catalog_router,
)
