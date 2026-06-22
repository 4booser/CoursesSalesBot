from app.handlers.course_parser import router as course_parser_router
from app.handlers.token import router as token_router


routers = (
    token_router,
    course_parser_router,
)
