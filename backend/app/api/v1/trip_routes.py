"""
行程规划相关接口：/api/v1/trips/*
"""


from typing import List
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.agents.workflows.trip_planning_chain import run_trip_planning
from app.middleware.auth import get_current_user
from app.models import ApiResponse
from app.models.trip_request import TripPlanRequest, TripPlanResponse
from app.observability.logger import default_logger as logger
from app.services.redis_service import redis_service

router = APIRouter(tags=["trip"])


@router.post(
    "/plan",
    summary="生成智能行程",
    response_model=ApiResponse[TripPlanResponse],
)
async def plan_trip(
    request: TripPlanRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[TripPlanResponse]:
    """
    根据目的地、日期、人数、预算与偏好，生成行程规划，并自动写入“我的行程”。
    内部调用 trip_planning_chain.run_trip_planning，返回与前端约定一致的 TripPlanResponse。
    """
    try:
        result = await run_trip_planning(request)

        # 为行程生成 ID 和创建时间，并写入 Redis，便于“我的行程”列表展示
        trip_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        result.id = trip_id
        result.created_at = created_at

        try:
            redis_service.store_trip(
                user_id=current_user["user_id"],
                trip_id=trip_id,
                trip_data=result.model_dump(),
            )
        except Exception as store_err:
            # 持久化失败不影响本次响应，只打日志，避免影响用户使用
            logger.exception("行程规划已生成，但写入 Redis 失败: %s", store_err)

        # 序列化前打点，便于排查“规划完成但前端 Network Error”（超时或序列化失败）
        logger.info("行程规划接口即将返回响应")
        return ApiResponse[TripPlanResponse](code=0, message="ok", data=result)
    except HTTPException:
        # 认证等 HTTP 异常直接抛出，交给上层处理
        raise
    except Exception as e:
        logger.exception("行程规划接口返回前异常: %s", e)
        # 交给全局异常处理器处理
        raise


@router.get("/list", summary="获取用户行程列表", response_model=List[TripPlanResponse])
async def get_user_trips_list(
    current_user: dict = Depends(get_current_user),
) -> List[TripPlanResponse]:
    """
    获取用户行程列表
    """
    try:
        return redis_service.list_user_trips(current_user["user_id"])
    except Exception as e:
        logger.exception("获取用户行程列表异常: %s", e)
        raise HTTPException(status_code=500, detail="获取用户行程列表异常")


@router.get(
    "/{trip_id}",
    summary="获取单个行程详情",
    response_model=TripPlanResponse,
)
async def get_trip_detail(
    trip_id: str,
    current_user: dict = Depends(get_current_user),
) -> TripPlanResponse:
    """
    根据行程ID获取单个行程详情。
    """
    try:
        trip_data = redis_service.get_trip(trip_id)
        if not trip_data:
            raise HTTPException(status_code=404, detail="行程不存在")

        # 简单的所有权校验（如果有 user_id 字段的话可以在这里校验）
        # 目前存储的数据里没有 user_id 字段，只通过 zset 维护归属，
        # 如果后续需要更严格校验，可以在 store_trip 时把 user_id 一并写入 trip_data。

        return TripPlanResponse(**trip_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取行程详情异常: %s", e)
        raise HTTPException(status_code=500, detail="获取行程详情异常")

