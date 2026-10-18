"""统一业务异常与响应包络:{code, message, data}。

错误码表见 docs/02-API约定.md 第 1.3 节。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """业务错误:HTTP 状态码 + 业务错误码 + 中文提示。"""

    def __init__(self, status_code: int, code: int, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


# 常用错误快捷构造
def bad_request(message: str) -> ApiError:
    return ApiError(400, 1001, message)


def unauthorized(message: str = "未登录或登录已过期") -> ApiError:
    return ApiError(401, 1002, message)


def forbidden(message: str = "没有权限执行此操作") -> ApiError:
    return ApiError(403, 1003, message)


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(404, 1004, message)


def conflict(code: int, message: str) -> ApiError:
    return ApiError(409, code, message)


def _envelope(code: int, message: str, data=None) -> dict:
    return {"code": code, "message": message, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        # 参数校验失败统一归入业务码 1001。
        # 只保留 JSON 安全字段：Pydantic v2 的 ctx 可能包含 ValueError 对象，
        # 直接塞进 JSONResponse 会导致序列化失败并变成 500。
        details = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors()[:5]
        ]
        return JSONResponse(status_code=400, content=_envelope(1001, "请求参数错误", details))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        mapping = {401: 1002, 403: 1003, 404: 1004}
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(mapping.get(exc.status_code, exc.status_code), str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content=_envelope(9001, "服务器内部错误"))