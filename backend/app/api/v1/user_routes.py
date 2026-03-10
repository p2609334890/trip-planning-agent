"""
用户相关接口占位：/api/v1/user/*
（用户偏好、登录/鉴权等后续实现）
"""

from fastapi import APIRouter

router = APIRouter(tags=["user"])


@router.get("", summary="用户信息占位")
async def user_info() -> dict:
    """占位接口，后续实现用户信息/偏好。"""
    return {"message": "user routes placeholder"}
