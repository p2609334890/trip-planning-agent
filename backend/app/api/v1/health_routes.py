"""
健康检查与版本信息：/api/v1/health
"""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("", summary="健康检查")
async def health_check() -> dict:
    """服务健康检查，返回 ok。"""
    return {"status": "ok"}
