"""
领域服务层：被 Agents/Tools 调用。
"""

from .llm_service import LLMService, get_llm_service
from .agent_sercvice import search_attractions, recommend_hotels, get_weather_forecast, estimate_budget, plan_route

__all__ = [
    "LLMService",
    "get_llm_service",
    "search_attractions",
    "recommend_hotels",
    "get_weather_forecast",
    "estimate_budget",
    "plan_route",
]
