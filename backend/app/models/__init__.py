"""
Pydantic 数据模型：请求/响应/领域对象。
"""

from .trip_request import TripPlanRequest
from .trip_plan import TripPlan, DayItinerary, BudgetSummary, MapPoint
from .common import ApiResponse, PageParams

__all__ = [
    "TripPlanRequest",
    "TripPlan",
    "DayItinerary",
    "BudgetSummary",
    "MapPoint",
    "ApiResponse",
    "PageParams",
]
