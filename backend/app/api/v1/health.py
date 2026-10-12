"""健康检查:供前端联通性测试与 SECoder 探活使用。"""

import time

from fastapi import APIRouter

from app.schemas.common import ApiResponse, ok

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=ApiResponse[dict])
async def health():
    return ok({"status": "up", "time": int(time.time())})