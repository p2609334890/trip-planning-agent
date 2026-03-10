"""
行程规划主工作流：多 Agent 架构。
由 1 个旅行规划 Agent 协调 3 个子专家（景点搜索、天气查询、酒店推荐），收集结果后生成最终行程。
"""

from pathlib import Path
from datetime import datetime, timedelta
import re

from app.models.trip_request import TripPlanRequest, TripPlanResponse
from app.agents.workflows.specialized_agents import TripPlannerAgent

async def run_trip_planning(request: TripPlanRequest) -> TripPlanResponse:
    """
    根据请求生成行程规划。
    多 Agent 架构：景点搜索专家、天气查询专家、酒店推荐专家并行执行，
    旅行规划 Agent 收集三者结果后生成最终行程并返回 TripPlanResponse（与前端约定一致）。
    """
    planner = TripPlannerAgent()
    return await planner.plan_trip_async(request)


