from typing import List, Optional

from app.models.common import Attraction, Location


def get_fallback_attractions(city: str, preferences: Optional[str] = None) -> List[Attraction]:
    """
    本地内置的一些示例景点数据，作为高德 API 调用失败时的回退。
    这里只放少量城市示例数据，避免在开发联调阶段因为网络/配额问题导致完全没有结果。
    """
    city = city.strip().lower()
    prefs = (preferences or "").lower()

    data: dict[str, list[dict]] = {
        "beijing": [
            {
                "name": "故宫博物院",
                "address": "北京市东城区景山前街4号",
                "lat": 39.916345,
                "lng": 116.397155,
                "visit_duration": 240,
                "description": "世界文化遗产，明清两代皇宫，了解中国古代宫廷文化的必游景点。",
                "rating": 4.8,
                "ticket_price": 60.0,
            },
            {
                "name": "天安门广场",
                "address": "北京市东城区长安街",
                "lat": 39.908722,
                "lng": 116.397499,
                "visit_duration": 90,
                "description": "世界上最大的城市广场之一，可以感受庄严的城市轴线与历史氛围。",
                "rating": 4.6,
                "ticket_price": 0.0,
            },
        ],
        "shanghai": [
            {
                "name": "外滩",
                "address": "上海市黄浦区中山东一路",
                "lat": 31.240118,
                "lng": 121.490317,
                "visit_duration": 120,
                "description": "沿黄浦江的经典步行观景带，可以看到万国建筑群和陆家嘴天际线。",
                "rating": 4.7,
                "ticket_price": 0.0,
            },
            {
                "name": "上海博物馆",
                "address": "上海市黄浦区人民大道201号",
                "lat": 31.228637,
                "lng": 121.475136,
                "visit_duration": 180,
                "description": "以中国古代艺术品为主的大型综合性博物馆，免费开放，适合半日游览。",
                "rating": 4.7,
                "ticket_price": 0.0,
            },
        ],
    }

    # 支持中文城市名的简单映射
    city_alias = {
        "北京": "beijing",
        "bj": "beijing",
        "上海": "shanghai",
        "sh": "shanghai",
    }
    key = city_alias.get(city, city)

    raw_list = data.get(key, [])

    # 简单根据偏好做一点过滤（例如 “博物馆”、“历史”、“夜景”等关键词）
    if prefs:
        filtered = []
        for item in raw_list:
            text = f"{item.get('name','')}{item.get('address','')}{item.get('description','')}".lower()
            if any(token in text for token in prefs.split()):
                filtered.append(item)
        if filtered:
            raw_list = filtered

    attractions: List[Attraction] = []
    for item in raw_list:
        attractions.append(
            Attraction(
                name=item["name"],
                address=item["address"],
                location=Location(lat=item["lat"], lng=item["lng"]),
                visit_duration=item.get("visit_duration", 120),
                description=item.get("description", ""),
                rating=item.get("rating", "N/A"),
                image_urls=[],
                ticket_price=item.get("ticket_price", 0.0),
            )
        )

    return attractions

