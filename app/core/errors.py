from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class Unauthorized(AppError):
    def __init__(self, message: str = "未授权") -> None:
        super().__init__("UNAUTHORIZED", message, 401)


class NotFound(AppError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__("NOT_FOUND", message, 404)


class Conflict(AppError):
    def __init__(self, message: str = "资源冲突") -> None:
        super().__init__("CONFLICT", message, 409)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id_ctx.get(),
            },
        )
