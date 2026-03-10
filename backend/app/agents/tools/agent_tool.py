from langchain_core.tools import tool
from app.models.common import Attraction, Hotel, BudgetSummary, Weather
from app.models.trip_request import TripPlanRequest
from app.services.agent_sercvice import search_attractions as search_attractions_service
from app.services.agent_sercvice import estimate_budget as estimate_budget_service
from app.services.agent_sercvice import plan_route as plan_route_service
from app.services.agent_sercvice import recommend_hotels as recommend_hotels_service
from app.services.agent_sercvice import get_weather_forecast as get_weather_forecast_service


@tool
def search_attractions(city: str, days: int, preferences: str) -> list[Attraction]:
    """
    根据城市、天数、偏好搜索景点信息
    """
    return search_attractions_service(city, days, preferences)   

@tool
def estimate_budget(trip_request: TripPlanRequest, attractions: list[Attraction], hotels: list[Hotel]) -> BudgetSummary:
    """
    根据行程请求、景点、酒店估算预算
    """
    return estimate_budget_service(trip_request, attractions, hotels)

@tool
def plan_route(points: list[dict]) -> dict:
    """
    根据点位列表返回路线规划参数（供前端地图渲染）。
    """
    return plan_route_service(points)

@tool
def recommend_hotels(city: str, budget: float, location_pref: str) -> list[Hotel]:
    """
    根据城市、预算、位置偏好推荐酒店
    """
    return recommend_hotels_service(city, budget, location_pref)

@tool
def get_weather(city: str) -> Weather:
    """
    根据城市查询天气信息
    """
    return get_weather_forecast_service(city)