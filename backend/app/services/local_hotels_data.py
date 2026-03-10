"""
本地兜底酒店数据：在高德/第三方 API 不可用或失败时返回示例酒店，便于联调与演示。
"""
from typing import List, Optional

from app.models.common import Hotel, Location


def get_fallback_hotels(
    city: str,
    budget: Optional[float] = None,
    location_pref: Optional[str] = None,
) -> List[Hotel]:
    """
    根据城市、预算、位置偏好返回内置示例酒店（仅作兜底）。
    """
    city_key = (city or "").strip().lower()
    city_alias = {"北京": "beijing", "bj": "beijing", "上海": "shanghai", "sh": "shanghai"}
    key = city_alias.get(city_key, city_key)

    # 示例数据：北京、上海各若干家，含价格区间与位置描述
    data: dict[str, list[dict]] = {
        "beijing": [
            {"name": "如家酒店(北京前门店)", "address": "北京市西城区前门大街", "lat": 39.896, "lng": 116.397, "price": "280", "rating": "4.2"},
            {"name": "汉庭酒店(北京天安门广场店)", "address": "北京市东城区东长安街", "lat": 39.908, "lng": 116.418, "price": "320", "rating": "4.3"},
            {"name": "全季酒店(北京王府井店)", "address": "北京市东城区王府井大街", "lat": 39.915, "lng": 116.412, "price": "450", "rating": "4.5"},
            {"name": "亚朵酒店(北京国贸店)", "address": "北京市朝阳区建国门外大街", "lat": 39.908, "lng": 116.458, "price": "580", "rating": "4.6"},
        ],
        "shanghai": [
            {"name": "如家酒店(上海南京路步行街店)", "address": "上海市黄浦区南京东路", "lat": 31.238, "lng": 121.488, "price": "300", "rating": "4.2"},
            {"name": "汉庭酒店(上海外滩店)", "address": "上海市黄浦区中山东一路", "lat": 31.240, "lng": 121.492, "price": "350", "rating": "4.4"},
            {"name": "全季酒店(上海陆家嘴店)", "address": "上海市浦东新区陆家嘴环路", "lat": 31.228, "lng": 121.505, "price": "480", "rating": "4.5"},
        ],
    }

    raw = data.get(key, [])
    hotels: List[Hotel] = []
    for item in raw:
        loc = Location(lat=item["lat"], lng=item["lng"])
        hotels.append(
            Hotel(
                name=item["name"],
                address=item.get("address", ""),
                location=loc,
                price=item.get("price", "N/A"),
                rating=item.get("rating", "N/A"),
                distance_to_main_attraction_km=None,
            )
        )
    return hotels
