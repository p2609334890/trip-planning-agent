"""
景点/酒店/预算/地图/天气等业务逻辑。
当前多数为占位实现，但会在被 Agent 的 Tools 调用时打印日志，便于观测。
"""

from datetime import datetime
from typing import Any, List
import logging
import os
import shlex
import requests
from app.config import settings
from app.models.common import Attraction, Location
from app.services.local_attractions_data import get_fallback_attractions

logger = logging.getLogger(__name__)

# 高德 WebService POI 搜索固定 URL
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"

def _poi_to_attraction(poi: dict) -> Attraction | None:
    """将高德 POI 单条转为 Attraction，解析失败返回 None。

    注意：此处不再进行图片搜索，图片将在行程规划完成后，
    针对最终选中的少量景点统一调用图片服务进行补充。
    """
    location_str = poi.get("location") or ""
    try:
        lng_str, lat_str = location_str.split(",")
        lng = float(lng_str)
        lat = float(lat_str)
    except Exception:
        return None
    address = poi.get("address") or ""
    if not address:
        address = f"{poi.get('pname','')}{poi.get('cityname','')}{poi.get('adname','')}"
    rating = "N/A"
    biz_ext = poi.get("biz_ext") or {}
    if isinstance(biz_ext, dict) and biz_ext.get("rating") not in (None, ""):
        try:
            rating = float(biz_ext["rating"])
        except (ValueError, TypeError):
            rating = biz_ext.get("rating", "N/A")

    return Attraction(
        name=poi.get("name", ""),
        address=address,
        location=Location(lat=lat, lng=lng),
        visit_duration=120,
        description=poi.get("type", "") or poi.get("typecode", ""),
        rating=rating,
        image_urls=[],
        ticket_price=float(0),
    )


def _fetch_amap_pois(city: str, keyword: str, limit: int) -> list[dict]:
    """对高德 POI 发一次请求，返回原始 pois 列表。"""
    params = {
        "key": settings.AMAP_API_KEY,
        "keywords": keyword,
        "city": city.strip(),
        "citylimit": "true",
        "offset": min(limit, 25),
        "page": 1,
        "output": "json",
    }
    try:
        resp = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("高德 POI 单次请求失败 keyword=%s: %s", keyword, e)
        return []
    if data.get("status") != "1":
        return []
    return data.get("pois", []) or []


"""
景点搜索逻辑。
按逗号拆分 preferences，多关键词各请求一次高德，合并去重后返回，保证数量且不依赖模型多次 tool call。
"""
def search_attractions(
    city: str,
    days: int,
    preferences: str | None = None,
    **kwargs: Any,
) -> list[Attraction]:
    """
    根据城市、天数、偏好检索景点候选。
    偏好按逗号拆成多关键词，每个关键词请求一次高德，结果按 POI id 去重合并后返回。
    """
    logger.info(
        "搜索景点: 城市={city}, 天数={days}, 偏好={preferences}",
        extra={"city": city, "days": days, "preferences": preferences},
    )

    # 根据行程天数估算总候选数量
    max_results = max(2, min(days * 4, 30))

    if not settings.AMAP_API_KEY:
        logger.warning("AMAP_API_KEY 未配置, 跳过高德地图请求.")
        fallback = get_fallback_attractions(city=city, preferences=preferences)
        return fallback

    # 按逗号拆分偏好，去空，无有效关键词时用「景点」
    raw = (preferences or "景点").replace("，", ",")
    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not keywords:
        keywords = ["景点"]

    # 每个关键词请求一次高德，单次最多取若干条（保证合并后总量可控）
    per_keyword = max(10, (max_results + len(keywords) - 1) // len(keywords))
    per_keyword = min(per_keyword, 25)

    seen_ids: set[str] = set()
    all_pois: list[dict] = []
    for kw in keywords:
        pois = _fetch_amap_pois(city, kw, limit=per_keyword)
        for p in pois:
            pid = p.get("id") or ""
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_pois.append(p)
        if len(all_pois) >= max_results:
            break

    logger.info(
        "高德地图多关键词合并: 关键词=%s, 去重后 %s 个景点.",
        keywords,
        len(all_pois),
        extra={"city": city, "keywords": keywords, "count": len(all_pois)},
    )

    attractions: List[Attraction] = []
    for poi in all_pois[:max_results]:
        a = _poi_to_attraction(poi)
        if a is not None:
            attractions.append(a)

    if not attractions:
        return get_fallback_attractions(city=city, preferences=preferences)
    return attractions




from typing import Any, List
from app.models.common import Hotel, Location
from app.services.local_hotels_data import get_fallback_hotels

"""
酒店推荐逻辑。

根据城市、预算、位置偏好推荐酒店的几种比较好的方式：

方式一（当前实现）：高德 POI 搜索酒店
  - 与景点搜索共用 AMAP_API_KEY，keywords 由「酒店/宾馆」+ 预算档位 + 位置偏好组成。
  - 预算映射：<300 经济型，300–600 舒适型，>600 高档/星级；位置偏好直接拼入关键词（如商圈、景区附近）。
  - 无 key 或请求失败时回退到本地兜底数据。

方式二：接入 OTA/酒店 API（携程、飞猪、Booking 等）
  - 优点：真实房态、价格、点评；可做预订跳转。
  - 需申请开放平台 key、处理配额与合规。

方式三：高德 POI + 距离排序（结合景点）
  - 先拿到行程中的景点坐标，再搜酒店，按「距离主要景点距离」排序，适合「住得离景区近」的偏好。

方式四：多源聚合 + 去重
  - 同时调高德、百度 POI 或本地知识库，按名称/地址去重后合并，再按评分或价格排序。

方式五：纯 LLM/知识库推荐
  - 用本地向量库或 LLM 根据城市+预算+偏好生成酒店名单（无实时价格），适合冷启动或演示。
"""

# 高德 POI 与景点共用 base URL
AMAP_HOTEL_DEFAULT_KEYWORDS = "酒店"

def _budget_to_keyword(budget: float | None) -> str:
    """按预算档位返回高德搜索关键词，便于筛出大致价位酒店。"""
    if budget is None or budget <= 0:
        return ""
    if budget < 300:
        return "经济型酒店"
    if budget < 600:
        return "舒适型酒店"
    return "高档酒店"


def recommend_hotels(
    city: str,
    budget: float | None = None,
    location_pref: str | None = None,
    **kwargs: Any,
) -> list[Hotel]:
    """
    根据城市、预算、位置偏好推荐酒店。
    优先高德 POI；无 key 或失败时使用本地兜底数据。
    """
    logger.info(
        "推荐酒店: 城市=%s, 预算=%s, 位置偏好=%s",
        city, budget, location_pref,
        extra={"city": city, "budget": budget, "location_pref": location_pref},
    )

    if not city or not city.strip():
        return get_fallback_hotels(city or "北京", budget, location_pref)

    if not settings.AMAP_API_KEY:
        logger.warning("AMAP_API_KEY 未配置，使用本地兜底酒店数据")
        return get_fallback_hotels(city, budget, location_pref)

    # 组合关键词：酒店 + 预算档位 + 位置偏好（如「景区附近」「市中心」）
    keyword_parts = [AMAP_HOTEL_DEFAULT_KEYWORDS]
    budget_kw = _budget_to_keyword(budget)
    if budget_kw:
        keyword_parts.append(budget_kw)
    if location_pref and str(location_pref).strip():
        keyword_parts.append(str(location_pref).strip())
    keywords = "".join(keyword_parts) if len(keyword_parts) > 1 else keyword_parts[0]

    params = {
        "key": settings.AMAP_API_KEY,
        "keywords": keywords,
        "city": city.strip(),
        "citylimit": "true",
        "offset": 15,
        "page": 1,
        "output": "json",
    }

    try:
        resp = requests.get(AMAP_PLACE_TEXT_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("高德酒店 POI 请求失败: %s", e)
        return get_fallback_hotels(city, budget, location_pref)

    if data.get("status") != "1":
        logger.warning("高德酒店 API 返回异常: %s", data)
        return get_fallback_hotels(city, budget, location_pref)

    pois = data.get("pois", []) or []
    hotels: List[Hotel] = []
    for poi in pois[:15]:
        location_str = poi.get("location") or ""
        try:
            lng_str, lat_str = location_str.split(",")
            lng = float(lng_str)
            lat = float(lat_str)
        except Exception:
            continue
        address = poi.get("address") or ""
        if not address:
            address = f"{poi.get('pname','')}{poi.get('cityname','')}{poi.get('adname','')}"
        rating = "N/A"
        biz_ext = poi.get("biz_ext") or {}
        if isinstance(biz_ext, dict) and biz_ext.get("rating") not in (None, ""):
            try:
                rating = str(float(biz_ext["rating"]))
            except (ValueError, TypeError):
                rating = str(biz_ext.get("rating", "N/A"))
        hotels.append(
            Hotel(
                name=poi.get("name", ""),
                address=address,
                location=Location(lat=lat, lng=lng),
                price="N/A",  # 高德 POI 一般不返价格，可后续接 OTA 补全
                rating=rating,
                distance_to_main_attraction_km=None,
            )
        )
    if not hotels:
        return get_fallback_hotels(city, budget, location_pref)
    return hotels








from typing import Any
from app.models.common import Weather
from app.config import settings
from huggingface_hub.inference._mcp.mcp_client import MCPClient
from huggingface_hub.inference._generated.types import ChatCompletionInputMessage, ChatCompletionStreamOutput
import asyncio
import json
"""
天气查询（通过彩云天气 MCP 工具）。
"""
async def _fetch_weather_via_mcp(city: str) -> dict[str, Any] | None:
    """
    通过 MCP（例如彩云天气 MCP）查询指定城市的天气信息。
    要求 MCP 端的工具能够根据城市名返回结构化天气数据。
    """
    # 构造允许的工具列表（从环境变量配置），可以是逗号分隔字符串或字符串列表，为空则不过滤
    raw = settings.TRAVEL_MCP_ALLOWED_TOOLS
    allowed_tools: list[str] | None
    if isinstance(raw, list):
        allowed_tools = [str(t).strip() for t in raw if str(t).strip()] or None
    else:
        allowed_tools_raw = (raw or "").strip()
        allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()] or None

    async with MCPClient(
        model=settings.LLM_MODEL_ID,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
    ) as client:
        # 连接 MCP Server（彩云天气 MCP）。支持三种类型：http / sse / stdio。
        server_type = (settings.TRAVEL_MCP_SERVER_TYPE or "stdio").strip().lower()
        server_url = (getattr(settings, "TRAVEL_MCP_SERVER_URL", "") or "").strip()

        if server_type == "http":
            if not server_url:
                return None
            await client.add_mcp_server(
                type="http",
                url=server_url,
                allowed_tools=allowed_tools,
            )
        elif server_type == "sse":
            if not server_url:
                return None
            await client.add_mcp_server(
                type="sse",
                url=server_url,
                allowed_tools=allowed_tools,
            )
        elif server_type == "stdio":
            # 本地 stdio 启动 Node 版彩云 MCP：默认使用 `node mcp/caiyun-weather-mcp/dist/index.js`
            command = getattr(settings, "TRAVEL_MCP_COMMAND", None) or "node"
            args_raw = getattr(settings, "TRAVEL_MCP_COMMAND_ARGS", None)
            if isinstance(args_raw, str) and args_raw.strip():
                args = shlex.split(args_raw.strip())
            else:
                # 默认相对于 backend 工作目录
                args = ["mcp/caiyun-weather-mcp/dist/index.js"]

            # 组装环境变量：优先使用进程环境，其次使用 settings 中的配置
            env: dict[str, str] = {}
            caiyun_key = os.environ.get("CAIYUN_API_KEY") or getattr(
                settings, "CAIYUN_API_KEY", None
            )
            if caiyun_key:
                env["CAIYUN_API_KEY"] = str(caiyun_key)
            if settings.AMAP_API_KEY:
                env["AMAP_API_KEY"] = settings.AMAP_API_KEY

            await client.add_mcp_server(
                type="stdio",
                command=command,
                args=args,
                env=env,
                allowed_tools=allowed_tools,
            )
        else:
            return None

        # 提示模型必须调用彩云天气相关工具，并按 Weather 模型结构返回 JSON
        messages: list[ChatCompletionInputMessage] = [
            ChatCompletionInputMessage.parse_obj_as_instance(
                {
                    "role": "system",
                    "content": (
                        "你是天气查询助手，必须通过已连接的彩云天气 MCP 工具获取真实天气，"
                        "绝不能凭空编造。请查询指定城市今天的天气，并只返回一个 JSON 对象，"
                        "字段严格为：date(日期字符串，格式YYYY-MM-DD)、"
                        "day_weather(白天天气现象)、night_weather(夜间天气现象)、"
                        "day_temp(白天温度的数字字符串，不要带单位)、"
                        "night_temp(夜间温度的数字字符串，不要带单位)、"
                        "day_wind(白天风向和风力描述)、night_wind(夜间风向和风力描述)。"
                    ),
                }
            ),
            ChatCompletionInputMessage.parse_obj_as_instance(
                {
                    "role": "user",
                    "content": f"查询{city}今天的天气，严格按照格式返回 JSON 对象。",
                }
            ),
        ]

        # 运行带工具的单轮对话。
        # MCPClient 当前实现为：模型触发工具后，直接返回 role="tool" 的消息作为最终结果，
        # 并不会再自动让模型基于工具结果生成一条新的 assistant 回复。
        # 因此我们优先从工具消息中解析 JSON；若没有工具消息，再尝试解析助手文本。
        last_assistant_content: str = ""
        tool_content: str | None = None

        async for chunk in client.process_single_turn_with_tools(messages):
            if isinstance(chunk, ChatCompletionStreamOutput):
                # 流式 delta，取其中的内容增量（一般是“正在调用工具……”之类的文本）
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    last_assistant_content += delta.content
            elif isinstance(chunk, ChatCompletionInputMessage):
                # 工具结果或最终 assistant 消息
                if chunk.role == "tool" and isinstance(chunk.content, str):
                    # 彩云 MCP 工具返回的 content 本身是 JSON 字符串，这里直接记录下来
                    tool_content = chunk.content
                elif chunk.role == "assistant" and isinstance(chunk.content, str):
                    last_assistant_content = chunk.content

        # 优先使用工具返回的内容解析 JSON
        text_source = tool_content or last_assistant_content

        if not text_source:
            return None
        logger.info("彩云天气 MCP 返回内容: %s", text_source)
        text = text_source.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试从 ```json``` 或第一个 { ... } 中抽取
            import re

            block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if block:
                raw = block.group(1).strip()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass

            start = text.find("{")
            if start >= 0:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start : i + 1])
                            except json.JSONDecodeError:
                                break

        return None


def get_weather_forecast(
    city: str,
    date_range: tuple[str, str] | None = None,
    **kwargs: Any,
) -> Weather:
    """
    同步封装：通过彩云天气 MCP 工具查询真实天气信息。
    若 MCP 查询失败，则使用占位天气结果。
    """
    try:
        # 在大多数同步业务环境下都可以直接 asyncio.run
        data = asyncio.run(_fetch_weather_via_mcp(city))
    except RuntimeError:
        # 若当前已经存在事件循环（例如在某些异步环境中），
        # 为避免嵌套事件循环错误，此时直接返回一个占位天气并记录日志。
        logger.warning("当前存在事件循环，暂不支持在该上下文中通过 MCP 查询天气")
        data = None
    except Exception as e:
        logger.warning("通过彩云天气 MCP 查询天气失败: %s", e)
        data = None

    return _build_weather_from_mcp_data(data)


def _build_weather_from_mcp_data(data: Any) -> Weather:
    """将 MCP 返回的数据安全映射到 Weather 模型，失败时返回占位天气。

    优先支持两种格式：
    1）已经是目标格式的精简 JSON（包含 date/day_weather/day_temp 等字段）；
    2）彩云天气原始结构（包含 realtime / daily.forecast 等字段）。
    """

    def _fallback() -> Weather:
        logger.info("彩云天气 MCP 未返回有效或可解析的数据，使用占位天气结果")
        return Weather(
            date=datetime.now().strftime("%Y-%m-%d"),
            day_weather="未知",
            night_weather="未知",
            day_temp="0",
            night_temp="0",
            day_wind=None,
            night_wind=None,
        )

    if not isinstance(data, dict):
        return _fallback()

    def _to_str(v: Any, default: str = "") -> str:
        if v is None:
            return default
        return str(v)

    # 情况一：已经是精简 JSON，直接映射
    if "date" in data and "day_weather" in data and "day_temp" in data:
        return Weather(
            date=_to_str(data.get("date"), datetime.now().strftime("%Y-%m-%d")),
            day_weather=_to_str(data.get("day_weather"), "未知"),
            night_weather=_to_str(data.get("night_weather"), "未知"),
            day_temp=_to_str(data.get("day_temp"), "0"),
            night_temp=_to_str(data.get("night_temp"), "0"),
            day_wind=data.get("day_wind"),
            night_wind=data.get("night_wind"),
        )

    # 情况二：彩云天气原始结构，尝试从 daily.forecast[0] 抽取
    try:
        daily = data.get("daily") or {}
        forecasts = daily.get("forecast") or []
        first = forecasts[0] if forecasts else None
        if not isinstance(first, dict):
            return _fallback()

        # 日期：彩云为 2026-03-13T00:00+08:00，截取前 10 位
        raw_date = _to_str(first.get("date"), datetime.now().strftime("%Y-%m-%d"))
        date_str = raw_date[:10] if len(raw_date) >= 10 else raw_date

        # 天气现象
        day_weather = _to_str(
            first.get("weather_day") or first.get("weather") or "未知",
            "未知",
        )
        night_weather = _to_str(
            first.get("weather_night") or first.get("weather") or "未知",
            "未知",
        )

        # 温度：使用 temperature.max / min
        temp_obj = first.get("temperature") or {}

        def _to_temp(v: Any, default: str = "0") -> str:
            if v is None:
                return default
            try:
                # 尽量取整，避免 14.79 之类的小数
                f = float(v)
                i = int(round(f))
                return str(i)
            except (TypeError, ValueError):
                return _to_str(v, default)

        day_temp = _to_temp(temp_obj.get("max"), "0")
        night_temp = _to_temp(temp_obj.get("min"), "0")

        # 风：优先用 wind_day / wind_night，其次用 wind
        def _format_wind(raw: Any) -> str | None:
            if raw is None:
                return None
            if isinstance(raw, str):
                return raw or None
            if isinstance(raw, dict):
                speed = raw.get("speed")
                direction = raw.get("direction")
                parts: list[str] = []
                try:
                    if direction is not None:
                        parts.append(f"{float(direction):.0f}度")
                except (TypeError, ValueError):
                    pass
                try:
                    if speed is not None:
                        parts.append(f"{float(speed):.1f}m/s")
                except (TypeError, ValueError):
                    pass
                return " ".join(parts) or None
            return _to_str(raw)

        day_wind = _format_wind(first.get("wind_day") or first.get("wind"))
        night_wind = _format_wind(first.get("wind_night") or first.get("wind"))

        return Weather(
            date=date_str,
            day_weather=day_weather,
            night_weather=night_weather,
            day_temp=day_temp,
            night_temp=night_temp,
            day_wind=day_wind,
            night_wind=night_wind,
        )
    except Exception as e:
        logger.warning("解析彩云天气原始结构失败，将使用占位天气: %s", e)
        return _fallback()


async def get_weather_forecast_async(
    city: str,
    date_range: tuple[str, str] | None = None,
    **kwargs: Any,
) -> Weather:
    """
    异步版天气查询：在已有事件循环（如 Starlette/FastAPI 路由、Agent 内部）中使用。
    """
    try:
        data = await _fetch_weather_via_mcp(city)
    except Exception as e:
        logger.warning("通过彩云天气 MCP 查询天气失败(异步): %s", e)
        data = None

    return _build_weather_from_mcp_data(data)



from typing import Any
from math import radians, sin, cos, asin, sqrt
from datetime import datetime
from app.models.common import BudgetSummary

"""
成本估算逻辑：机酒+门票+交通+餐饮。
这里提供一个基于城市 + 行程天数 + 景点/酒店信息的简单规则实现，
保证在没有外部报价 API 的情况下也能给出可视化预算数字。
"""


class BudgetService:
    """按简单规则估算行程预算。"""

    # 非精确城市级基准价，可后续挪到配置或数据库里
    _CITY_BASE_PRICES: dict[str, dict[str, float]] = {
        "beijing": {"hotel": 450.0, "food": 130.0, "transport": 60.0, "tickets": 100.0},
        "shanghai": {"hotel": 500.0, "food": 150.0, "transport": 70.0, "tickets": 110.0},
        "default": {"hotel": 400.0, "food": 120.0, "transport": 60.0, "tickets": 90.0},
    }

    _BUDGET_LEVEL_FACTOR: dict[str, float] = {
        "经济": 0.8,
        "经济型": 0.8,
        "适中": 1.0,
        "中等": 1.0,
        "豪华": 1.8,
        "高端": 1.8,
    }

    def _safe_get(self, obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if hasattr(obj, key):
            return getattr(obj, key, default)
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    def _trip_days(self, trip_request: Any) -> int:
        """根据 start_date / end_date 计算行程天数，失败时回退为 1 天。"""
        start = self._safe_get(trip_request, "start_date")
        end = self._safe_get(trip_request, "end_date")
        if not start or not end:
            return 1
        try:
            d1 = datetime.strptime(str(start), "%Y-%m-%d")
            d2 = datetime.strptime(str(end), "%Y-%m-%d")
            return max(1, (d2 - d1).days + 1)
        except Exception:
            return 1

    def _city_key(self, destination: str | None) -> str:
        if not destination:
            return "default"
        name = str(destination).strip().lower()
        alias = {
            "北京": "beijing",
            "bj": "beijing",
            "shanghai": "shanghai",
            "上海": "shanghai",
            "sh": "shanghai",
        }
        return alias.get(name, name) if name in self._CITY_BASE_PRICES else "default"

    def _budget_factor(self, trip_request: Any) -> float:
        level = self._safe_get(trip_request, "budget", "中等")
        level = str(level or "中等")
        for k, factor in self._BUDGET_LEVEL_FACTOR.items():
            if k in level:
                return factor
        return 1.0

    def _estimate_ticket_per_day(self, days: int, attractions: list[dict] | None) -> float:
        """根据景点 ticket_price 粗略估算每天门票花费。"""
        if not attractions:
            return 0.0
        prices: list[float] = []
        for a in attractions:
            try:
                price = a.get("ticket_price") if isinstance(a, dict) else getattr(a, "ticket_price", None)
            except Exception:
                price = None
            if price is None:
                continue
            try:
                prices.append(float(price))
            except (TypeError, ValueError):
                continue
        if not prices:
            return 0.0
        avg_ticket = sum(prices) / len(prices)
        # 粗略假设每天游玩 2~3 个收费景点
        attractions_per_day = max(1, min(3, len(prices) // max(1, days)))
        return avg_ticket * attractions_per_day

    def _estimate_hotel_per_day(self, city_key: str, hotels: list[dict] | None) -> float:
        """优先使用酒店列表中的价格估算每晚房费，失败时回退到城市基准价。"""
        if hotels:
            nums: list[float] = []
            for h in hotels:
                try:
                    price = h.get("price") if isinstance(h, dict) else getattr(h, "price", None)
                except Exception:
                    price = None
                if price in (None, "", "N/A"):
                    continue
                try:
                    nums.append(float(price))
                except (TypeError, ValueError):
                    continue
            if nums:
                return sum(nums) / len(nums)
        base = self._CITY_BASE_PRICES.get(city_key) or self._CITY_BASE_PRICES["default"]
        return base["hotel"]

    def estimate(
        self,
        trip_request: Any,
        attractions: list[dict] | None = None,
        hotels: list[dict] | None = None,
    ) -> BudgetSummary:
        days = self._trip_days(trip_request)
        destination = self._safe_get(trip_request, "destination", "未知城市")
        city_key = self._city_key(destination)
        base = self._CITY_BASE_PRICES.get(city_key) or self._CITY_BASE_PRICES["default"]
        factor = self._budget_factor(trip_request)

        hotel_per_day = self._estimate_hotel_per_day(city_key, attractions if hotels is None else hotels)
        ticket_per_day = self._estimate_ticket_per_day(days, attractions)

        transport_per_day = base["transport"] * factor
        food_per_day = base["food"] * factor
        hotel_per_day *= factor
        ticket_per_day *= max(0.6, min(1.4, factor))

        transport_total = transport_per_day * days
        dining_total = food_per_day * days
        hotel_total = hotel_per_day * days
        tickets_total = ticket_per_day * days
        other_total = 0.0

        total = transport_total + dining_total + hotel_total + tickets_total + other_total

        result: BudgetSummary = {
            "transport": round(transport_total, 2),
            "food": round(dining_total, 2),
            "hotel": round(hotel_total, 2),
            "tickets": round(tickets_total, 2),
            "other": round(other_total, 2),
            "total": round(total, 2),
        }
        return result


_budget_service = BudgetService()


def estimate_budget(
    trip_request: Any,
    attractions: list[dict] | None = None,
    hotels: list[dict] | None = None,
    **kwargs: Any,
) -> BudgetSummary:
    """
    估算总预算及分项（住宿、交通、门票、餐饮等），
    返回简单可视化的预算字典，键包括:
    - transport: 交通
    - food: 餐饮
    - hotel: 住宿
    - tickets: 景点门票
    - other: 其他
    - total: 总计
    """
    logger.info(
        "估算预算: 行程请求=%s, 景点数=%s, 酒店数=%s",
        trip_request,
        len(attractions or []),
        len(hotels or []),
    )
    return _budget_service.estimate(trip_request, attractions, hotels)


"""
地图服务：POI、路线、坐标转换、静态图/前端渲染参数。
这里提供一个基于经纬度的简单路线规划，前端至少可以画出 polyline，
后续接入高德/百度真实路线 API 时可以无缝替换内部实现。
"""


class RouteService:
    """根据点位列表生成简单 polyline 与距离/时间估算。"""

    def _haversine_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """球面距离估算，单位公里。"""
        rlat1, rlng1, rlat2, rlng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = rlat2 - rlat1
        dlng = rlng2 - rlng1
        a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
        c = 2 * asin(sqrt(a))
        return 6371.0 * c

    def plan(self, points: list[dict], mode: str = "driving") -> dict:
        """
        根据点位列表返回路线规划参数（供前端地图渲染）。

        返回结构示例:
        {
          "polyline": [{"lat": ..., "lng": ...}, ...],
          "distance_km": 12.3,
          "estimated_travel_minutes": 45,
          "segments": [
             {"from": {...}, "to": {...}, "distance_km": 3.2, "estimated_travel_minutes": 10},
             ...
          ],
        }
        """
        if not points:
            return {"polyline": [], "distance_km": 0.0, "estimated_travel_minutes": 0, "segments": []}

        polyline: list[dict] = []
        segments: list[dict] = []
        total_distance_km = 0.0

        for p in points:
            try:
                lat = float(p.get("lat") or p.get("latitude"))
                lng = float(p.get("lng") or p.get("longitude"))
            except Exception:
                # 跳过经纬度缺失或格式不正确的点
                continue
            polyline.append({"lat": lat, "lng": lng, "name": p.get("name")})

        if len(polyline) < 2:
            return {"polyline": polyline, "distance_km": 0.0, "estimated_travel_minutes": 0, "segments": []}

        for i in range(len(polyline) - 1):
            a = polyline[i]
            b = polyline[i + 1]
            d = self._haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
            total_distance_km += d
            # 简单速度假设：城市自驾 30km/h，步行 4km/h
            if mode == "walking":
                minutes = d / 4.0 * 60.0
            else:
                minutes = d / 30.0 * 60.0
            segments.append(
                {
                    "from": a,
                    "to": b,
                    "distance_km": round(d, 3),
                    "estimated_travel_minutes": int(round(minutes)),
                }
            )

        if mode == "walking":
            total_minutes = total_distance_km / 4.0 * 60.0
        else:
            total_minutes = total_distance_km / 30.0 * 60.0

        return {
            "polyline": polyline,
            "distance_km": round(total_distance_km, 3),
            "estimated_travel_minutes": int(round(total_minutes)),
            "segments": segments,
            "mode": mode,
        }


_route_service = RouteService()


def plan_route(points: list[dict], **kwargs: Any) -> dict:
    """
    根据点位列表返回路线规划参数（供前端地图渲染）。
    kwargs 中可以传入 mode="driving" / "walking" 等简单模式。
    """
    mode = kwargs.get("mode", "driving")
    logger.info("规划路线: 点位数=%s, mode=%s", len(points or []), mode)
    return _route_service.plan(points, mode=mode)

# def geocode(address: str, **kwargs: Any) -> dict:
#     """
#     地址转经纬度。
#     """
#     logger.info(f"地址转经纬度: 地址={address}")
#     return {}