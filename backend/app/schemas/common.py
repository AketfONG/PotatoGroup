"""统一响应包络与通用模型。"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """所有 REST 接口的统一响应包络,见 docs/02-API约定.md 1.2 节。"""

    code: int = 0
    message: str = "ok"
    data: Optional[DataT] = None


def ok(data=None, message: str = "ok"):
    return ApiResponse(code=0, message=message, data=data)