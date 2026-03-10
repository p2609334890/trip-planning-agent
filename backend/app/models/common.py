"""
通用响应模型、分页等。
"""

from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel, Field

T = TypeVar("T")
BudgetSummary = dict[str, float]

class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应外壳。"""
    code: int = Field(0, description="业务码，0 表示成功")
    message: str = Field("ok", description="提示信息")
    data: Optional[T] = Field(None, description="业务数据")

class PageParams(BaseModel):
    """分页参数。"""
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, ge=1, le=100, description="每页条数")




class Location(BaseModel):
    """地理位置模型"""
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")

class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    visit_duration: int = Field(..., description="建议游览时间(分钟)", gt=0)
    description: str = Field(..., description="景点描述")
    # category: Optional[str] = Field(default="景点",description="景点类别")
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="评分")
    image_urls: List[str] = Field(default_factory=list, description="图片URL 列表")
    ticket_price: Optional[float] = Field(default=None, ge=0, description="门票价格(元)")


class Hotel(BaseModel):
    """酒店信息模型"""
    name: str = Field(..., description="酒店名称")
    address: str = Field("", description="地址")
    location: Location | None = Field(default=None, description="地理位置坐标")
    price: float | str = Field("N/A", description="价格")
    rating: float | str = Field("N/A", description="评分")
    distance_to_main_attraction_km: float | None = Field(
        default=None,
        description="距离主要景点的距离（单位：公里），用于推荐离景点更近的酒店",
    )

class Dining(BaseModel):
    """餐饮信息模型"""
    name: str = Field(..., description="餐厅名称")
    address: str = Field("", description="地址")
    location: Location | None = None
    cost_per_person: float | str = Field("N/A", description="人均消费")
    rating: float | str = Field("N/A", description="评分")

class Weather(BaseModel):
    """天气信息模型"""
    date: str = Field(..., description="日期")
    day_weather: str = Field(..., description="白天天气现象")
    night_weather: str = Field(..., description="夜间天气现象")
    day_temp: str = Field(..., description="白天温度（数值字符串，例如 25）")
    night_temp: str = Field(..., description="夜间温度（数值字符串，例如 15）")
    day_wind: str | None = Field(
        default=None, description="白天风向与风力描述，例如 东风3级"
    )
    night_wind: str | None = Field(
        default=None, description="夜间风向与风力描述，例如 西北风2级"
    )


