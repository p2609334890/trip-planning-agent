"""
行程规划主工作流：LangGraph 预置 ReAct Agent。
规划 Agent 通过工具拉取景点 / 天气 / 酒店数据，再生成符合约定的行程 JSON。
"""

from pathlib import Path
from datetime import datetime, timedelta
import re

from app.models.trip_request import TripPlanRequest, TripPlanResponse
from app.agents.workflows.specialized_agents import TripPlannerAgent

async def run_trip_planning(request: TripPlanRequest) -> TripPlanResponse:
    """
    根据请求生成行程规划。
    使用 LangGraph create_react_agent：模型按需调用工具获取真实数据后输出 TripPlanResponse 所需结构。
    """
    planner = TripPlannerAgent()
    return await planner.plan_trip_async(request)


