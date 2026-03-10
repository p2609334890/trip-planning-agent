"""
行程规划结果模型：按天行程、景点/酒店、预算、地图点位等。
"""

from typing import Optional
from pydantic import BaseModel, Field


class MapPoint(BaseModel):
    """地图点位：用于前端打点与路线。"""
    name: str = Field(..., description="点位名称")
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")
    type: Optional[str] = Field(None, description="类型：attraction / hotel / restaurant 等")


class DayItinerary(BaseModel):
    """单日行程。"""
    day: int = Field(..., description="第几天")
    date: Optional[str] = Field(None, description="日期")
    summary: Optional[str] = Field(None, description="当日概要")
    items: list[dict] = Field(default_factory=list, description="当日行程项（时间、地点、说明）")
    map_points: list[MapPoint] = Field(default_factory=list, description="当日涉及的地图点位")


class BudgetSummary(BaseModel):
    """预算汇总。"""
    total: Optional[float] = Field(None, description="总预算/预估总花费")
    accommodation: Optional[float] = Field(None, description="住宿")
    transport: Optional[float] = Field(None, description="交通")
    tickets: Optional[float] = Field(None, description="门票")
    food: Optional[float] = Field(None, description="餐饮")
    other: Optional[float] = Field(None, description="其他")


class TripPlan(BaseModel):
    """行程规划结果：按天行程、预算汇总、地图点位。"""

    title: Optional[str] = Field(None, description="行程标题")
    destination: Optional[str] = Field(None, description="目的地")
    days: list[DayItinerary] = Field(default_factory=list, description="按天行程列表")
    budget: Optional[BudgetSummary] = Field(None, description="预算汇总")
    map_points: list[MapPoint] = Field(default_factory=list, description="全行程地图点位（可选，也可从 days 聚合）")
    tips: Optional[str] = Field(None, description="小贴士/注意事项")
