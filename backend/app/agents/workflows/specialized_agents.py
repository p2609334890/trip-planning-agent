"""
"""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage

from app.config import settings
from app.observability.logger import default_logger as logger
from app.models.trip_request import (
    TripPlanRequest,
    TripPlanResponse,
    BudgetBreakdown,
    DailyPlan,
    DailyBudget,
)
from app.models.common import Location, Hotel, Weather, Attraction, Dining
from app.agents.tools import agent_tool
from app.services.agent_sercvice import recommend_hotels as recommend_hotels_service
from app.services.agent_sercvice import search_attractions as search_attractions_service
from app.services.agent_sercvice import (
    get_weather_forecast as get_weather_forecast_service,
    get_weather_forecast_async as get_weather_forecast_service_async,
)




from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory

from app.services.retrieval_service import vector_memory_service  # 复用向量记忆
# ============ Agent提示词 ============


ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
1. 你必须使用工具来搜索景点!不要自己编造景点信息!
2. 你应该参考用户的历史偏好和相似行程来优化搜索策略
3. 如果从上下文信息中了解到用户喜欢特定类型的景点，优先搜索这些类型
4. 搜索完成后，将结果共享给其他智能体

**工具调用格式:**
使用maps_text_search工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=景点关键词,city=城市名]`

**示例:**
用户: "搜索北京的历史文化景点"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=历史文化,city=北京]

用户: "搜索上海的公园"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=公园,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 参数用逗号分隔
4. 如果用户有历史偏好，优先使用这些偏好作为搜索关键词
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
1. 你必须使用工具来查询天气!不要自己编造天气信息!
2. 你应该查询整个行程期间的天气，而不仅仅是当前日期
3. 查询完成后，将天气信息共享给规划智能体

**工具调用格式:**
使用maps_weather工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_weather:city=城市名]`

**示例:**
用户: "查询北京天气"
你的回复: [TOOL_CALL:amap_maps_weather:city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
1. 你必须使用工具来搜索酒店!不要自己编造酒店信息!
2. 你应该参考景点智能体提供的景点位置信息，优先推荐距离景点较近的酒店
3. 你应该参考用户的酒店偏好和历史选择来优化推荐
4. 推荐完成后，将结果共享给规划智能体

**工具调用格式:**
使用maps_text_search工具搜索酒店时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=酒店,city=城市名]`

**示例:**
用户: "搜索北京的酒店"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=酒店,city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 关键词使用"酒店"或"宾馆"
4. 如果从上下文了解到景点位置，优先搜索附近的酒店
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息、酒店信息和天气信息，生成详细的旅行计划。

**重要提示:**
1. 你应该参考用户的历史行程和反馈来优化规划策略
2. 你应该考虑从其他智能体共享的信息（景点位置、酒店位置等）
3. 如果发现信息不足，可以请求其他智能体提供更多信息
4. 生成计划后，可以与其他智能体协商优化方案

**地理位置和距离要求（非常重要）:**
1. **所有景点必须在目标城市范围内**：严格验证每个景点的地理位置（经纬度），确保所有景点都在用户指定的目的地城市，绝对不要推荐其他城市的景点。
2. **同一天景点距离控制**：同一天内的景点之间距离要合理，建议不超过50公里，优先安排距离较近的景点在同一天游览。
3. **相邻天景点距离控制**：相邻两天的景点之间距离也要合理，避免第一天在城市的东边，第二天突然跳到城市的西边，建议相邻天的主要景点距离不超过100公里。
4. **地理位置验证**：在生成行程前，必须验证所有景点的经纬度是否在目标城市的合理范围内。如果发现景点位置异常（如规划杭州之旅却出现福建的景点），必须排除该景点或重新搜索。
5. **路线优化**：按照地理位置合理安排景点顺序，尽量形成一条合理的游览路线，减少往返路程。

请严格按照以下 **JSON 结构** 返回旅行计划。你的输出必须是有效的 JSON，不要添加任何额外的解释或注释。

**整体设计要求：**
1. **景点模型（Attraction）** 必须包含：景点名称、类型、评分、建议游玩时间、描述、地址、经纬度、景点图片 URL 列表、门票价格。
2. **酒店模型（Hotel）** 在原有基础上，必须补充「距离景点的距离」字段。
3. **单日行程（DailyPlan）** 必须包含：
   - 推荐住宿（recommended_hotel）
   - 景点列表（attractions）
   - 餐饮列表（dinings）
   - 单日预算拆分（budget），包括交通费用、餐饮费用、酒店费用、景点门票费用。
4. **预算**：总预算字段需要拆分为交通费用、餐饮费用、酒店费用、景点门票费用四项，并给出总和。
5. 所有的「图片」只能挂在 **景点（attractions）** 上，不能给酒店或餐饮生成图片 URL。

**响应格式（仅文字说明，字段名和类型必须严格遵守）：**
返回的 JSON 根对象必须包含以下字段：
- "trip_title"：字符串，行程标题。
- "total_budget"：对象，包含 "transport_cost"、"dining_cost"、"hotel_cost"、"attraction_ticket_cost"、"total" 五个数值字段。
- "hotels"：数组，每个元素是酒店对象，包含名称、地址、经纬度、价格、评分、距离主要景点距离等字段。
- "days"：数组，每个元素是单日行程对象，包含 day、theme、weather、recommended_hotel、attractions、dinings、budget 等字段。

**关键要求：**
1. **trip_title**：创建一个吸引人且能体现行程特色的标题。
2. **total_budget**：给出四类费用（交通、餐饮、酒店、景点门票），并计算 total 为它们的总和。
3. **hotels / recommended_hotel**：酒店必须包含名称、地址、位置坐标、价格、评分和距离主要景点的距离。
4. **days**：为每一天创建详细的行程计划。
5. **theme**：每天的主题要体现该天的主要活动特色。
6. **weather**：包含该天的天气信息，温度必须是纯数字（不要带 °C 等单位），并给出白天和夜间的风向与风力（day_wind, night_wind）。
7. **attractions / dinings**：
   - attractions：只包含"景点"信息，图片 URL 只能出现在 attractions.image_urls 中。
   - dinings：只包含餐饮信息，不能包含图片 URL 字段。
8. **时间规划**：在描述中要体现出合理的时间安排（例如上午/下午/晚上安排哪些景点和餐饮）。
9. **预算准确**：total_budget.total 必须等于四类费用之和；每天的 budget.total 也必须等于四项之和。
10. **避免重复**：不要在多天中重复推荐同一个景点或餐厅。
11. **地理位置验证（关键）**：
    - 在生成JSON前，必须检查所有景点的location字段（经纬度）是否在目标城市范围内
    - 如果发现景点位置不在目标城市，必须排除该景点
    - 同一天的景点经纬度应该相对集中，距离不超过50公里
    - 相邻天的景点经纬度变化应该合理，避免突然跨越很大距离
"""
PEXELS_API_URL = settings.PEXELS_API_URL


def _get_llm():
    """统一 LLM 实例，供各 Agent 使用。"""
    return ChatOpenAI(
        model=settings.LLM_MODEL_ID,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.2,
        timeout=settings.LLM_TIMEOUT,
    )

#"""根据起止日期计算行程天数。"""
def _trip_days(request: TripPlanRequest) -> int:
    """根据起止日期计算行程天数。"""
    try:
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        end = datetime.strptime(request.end_date, "%Y-%m-%d")
        return max(1, (end - start).days + 1)
    except (ValueError, TypeError):
        return 1


#"""将预算描述转为大致数值（元），供酒店推荐等使用。"""
def _budget_to_float(budget: str) -> float:
    """将预算描述转为大致数值（元），供酒店推荐等使用。"""
    m = {"经济": 300, "经济型": 300, "中等": 500, "适中": 500, "豪华": 1200}
    return float(m.get(budget or "中等", 500))



#"""从规划 Agent 的回复中解析 JSON（支持 ```json ... ``` 包裹）。"""
def _parse_planner_json(raw: str) -> dict[str, Any] | None:
    """从规划 Agent 的回复中解析 JSON（支持 ```json ... ``` 包裹）。"""
    if not raw or not raw.strip():
        return None
    # 尝试提取 ```json ... ``` 代码块
    block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if block:
        raw = block.group(1).strip()
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 尝试从文本中找第一个 { ... } 结构
    start = raw.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


#"""将规划 Agent 输出的 JSON 转为 TripPlan 模型。"""
def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 60) -> int:
    """避免 LLM 返回 '约2小时' 等导致 int() 抛错。"""
    if v is None:
        return default
    try:
        if isinstance(v, (int, float)):
            return int(v) if v == int(v) else max(1, int(v))
        s = str(v).strip()
        if not s:
            return default
        return max(1, int(float(s)))
    except (TypeError, ValueError):
        return default


def _normalize_budget(raw: Any) -> dict[str, Any]:
    """将 LLM 可能返回的数字或字典统一为预算字典。"""
    if isinstance(raw, dict):
        return raw
    total = _safe_float(raw) if raw is not None else 0.0
    return {
        "transport_cost": 0.0,
        "dining_cost": 0.0,
        "hotel_cost": 0.0,
        "attraction_ticket_cost": 0.0,
        "total": total,
    }


def _planner_json_to_trip_plan_response(
    request: TripPlanRequest, data: dict[str, Any]
) -> TripPlanResponse:
    """将规划 Agent 输出的 JSON 转为前端期望的 TripPlanResponse。"""
    trip_title = data.get("trip_title") or f"{request.destination} 行程规划"
    tb = _normalize_budget(data.get("total_budget"))
    total_budget = BudgetBreakdown(
        transport_cost=_safe_float(tb.get("transport_cost")),
        dining_cost=_safe_float(tb.get("dining_cost")),
        hotel_cost=_safe_float(tb.get("hotel_cost")),
        attraction_ticket_cost=_safe_float(tb.get("attraction_ticket_cost")),
        total=_safe_float(tb.get("total")),
    )

    def _to_location(raw: Any) -> Location:
        if not raw or not isinstance(raw, dict):
            return Location(lat=0.0, lng=0.0)
        return Location(
            lat=_safe_float(raw.get("lat"), 0.0),
            lng=_safe_float(raw.get("lng"), 0.0),
        )

    def _to_attraction(a: dict) -> Attraction:
        loc = a.get("location") or {}
        raw_img = a.get("image_urls") or a.get("image_url")
        if isinstance(raw_img, list):
            image_urls = raw_img
        elif isinstance(raw_img, str):
            image_urls = [raw_img] if raw_img.strip() else []
        else:
            image_urls = []
        return Attraction(
            name=str(a.get("name", "") or ""),
            address=str(a.get("address", "") or ""),
            location=_to_location(loc),
            visit_duration=_safe_int(a.get("visit_duration"), 60),
            description=str(a.get("description", "") or ""),
            rating=a.get("rating", 0),
            image_urls=image_urls,
            ticket_price=a.get("ticket_price", 0),
        )

    def _to_hotel(h: dict) -> Hotel:
        loc = h.get("location") or {}
        return Hotel(
            name=h.get("name", ""),
            address=h.get("address", ""),
            location=_to_location(loc) if (loc.get("lat") is not None or loc.get("lng") is not None) else None,
            price=h.get("price", "N/A"),
            rating=h.get("rating", "N/A"),
            distance_to_main_attraction_km=h.get("distance_to_main_attraction_km"),
        )

    def _to_dining(d: dict) -> Dining:
        return Dining(
            name=d.get("name", ""),
            address=d.get("address", ""),
            location=_to_location(d.get("location")) if d.get("location") else None,
            cost_per_person=d.get("cost_per_person", "N/A"),
            rating=d.get("rating", "N/A"),
        )

    def _to_weather(w: dict) -> Optional[Weather]:
        if not w or not isinstance(w, dict):
            return None
        return Weather(
            date=w.get("date", ""),
            day_weather=w.get("day_weather", ""),
            night_weather=w.get("night_weather", ""),
            day_temp=str(w.get("day_temp", "")),
            night_temp=str(w.get("night_temp", "")),
            day_wind=w.get("day_wind"),
            night_wind=w.get("night_wind"),
        )

    hotels_data = data.get("hotels") or []
    hotels = [_to_hotel(h) for h in hotels_data if isinstance(h, dict)]

    days_data = data.get("days") or []
    days_list: list[DailyPlan] = []
    for i, d in enumerate(days_data):
        if not isinstance(d, dict):
            continue
        # 一些模型可能把 day 填成字符串日期，统一做安全整数转换，失败则回退为 i+1
        day_num = _safe_int(d.get("day"), i + 1)
        theme = d.get("theme") or f"第{day_num}天"
        day_budget = _normalize_budget(d.get("budget"))
        daily_budget = DailyBudget(
            transport_cost=_safe_float(day_budget.get("transport_cost")),
            dining_cost=_safe_float(day_budget.get("dining_cost")),
            hotel_cost=_safe_float(day_budget.get("hotel_cost")),
            attraction_ticket_cost=_safe_float(day_budget.get("attraction_ticket_cost")),
            total=_safe_float(day_budget.get("total")),
        )
        rec_hotel = d.get("recommended_hotel")
        recommended_hotel = _to_hotel(rec_hotel) if isinstance(rec_hotel, dict) else None
        weather: Optional[Weather] = _to_weather(d.get("weather")) if d.get("weather") else None
        attractions = [_to_attraction(a) for a in (d.get("attractions") or []) if isinstance(a, dict)]
        dinings = [_to_dining(x) for x in (d.get("dinings") or []) if isinstance(x, dict)]
        days_list.append(
            DailyPlan(
                day=day_num,
                theme=theme,
                weather=weather,
                recommended_hotel=recommended_hotel,
                attractions=attractions,
                dinings=dinings,
                budget=daily_budget,
            )
        )

    return TripPlanResponse(
        trip_title=trip_title,
        total_budget=total_budget,
        hotels=hotels,
        days=days_list,
    )


def _fetch_image_urls(query: str, per_page: int = 1) -> list[str]:
    """
    根据查询关键词调用 Pexels 搜索图片。
    返回若干张图片 URL（small/medium/large 等，优先 small）。
    """
    api_key = getattr(settings, "PEXELS_API_KEY", None)
    if not api_key:
        logger.debug("PEXELS_API_KEY 未配置，跳过图片搜索")
        return []
    try:
        resp = requests.get(
            f"{PEXELS_API_URL}/v1/search",
            params={"query": query, "per_page": per_page},
            headers={
                "Authorization": api_key,
            },
            timeout=50,
        )
        resp.raise_for_status()
        data = resp.json() or {}
        results = data.get("photos") or []
        urls: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            raw_urls = item.get("src") or {}
            if not isinstance(raw_urls, dict):
                continue
            # 优先使用 small，其次 medium/large，控制体积
            url = (
                raw_urls.get("small")
                or raw_urls.get("medium")
                or raw_urls.get("large")
            )
            if url:
                urls.append(url)
        return urls
    except Exception as e:
        logger.warning("Pexels 图片搜索失败 query=%s: %s", query, e)
        return []


def _enrich_trip_images(
    request: TripPlanRequest,
    resp: TripPlanResponse,
    max_total: int = 12,
    per_attraction: int = 1,
) -> TripPlanResponse:
    """
    在行程规划完成后，为部分景点补充/修正图片：
    - 仅针对最终行程中的景点
    - 控制最多请求 max_total 次，避免过多外部调用
    - 每个景点最多 per_attraction 张图片
    - 若已有图片但不是 Pexels 来源，尝试使用 Pexels 替换，避免 404/防盗链
    """
    if max_total <= 0 or per_attraction <= 0:
        return resp

    filled = 0
    city = (request.destination or "").strip()

    for day in resp.days:
        for attraction in day.attractions:
            if filled >= max_total:
                return resp

            # 读取当前图片列表
            cur_urls = getattr(attraction, "image_urls", []) or []
            has_valid_pexels = any(
                isinstance(u, str) and "images.pexels.com" in u for u in cur_urls
            )

            # 若已有 Pexels 图片，则不再补充
            if has_valid_pexels:
                continue

            name = (attraction.name or "").strip()
            if not name:
                continue

            query_parts = [city, name]
            query = " ".join([p for p in query_parts if p])
            if not query:
                continue

            urls = _fetch_image_urls(query, per_page=per_attraction)
            if urls:
                # 用 Pexels 结果覆盖原有非 Pexels 图片，避免 404/防盗链
                attraction.image_urls = urls
                filled += 1

    return resp


#"""行程规划 Agent：收集 3 个子专家结果，生成最终行程。"""

class TripPlannerAgent:
    """
    单体旅行规划 Agent（带对话记忆 + 向量记忆）：
    - 直接调用后端服务获取景点、天气、酒店等真实数据；
    - 使用向量记忆服务 VectorMemoryService 混合检索【用户历史 + 目的地知识】；
    - 通过 RunnableWithMessageHistory 维护多轮对话上下文；
    - 输出仍然是 TripPlanResponse，接口与原来保持一致。
    """

    def __init__(self) -> None:
        # 会话历史缓存：key = session_id（这里用 user_id 或 "anonymous"）
        self._histories: dict[str, InMemoryChatMessageHistory] = {}

        # 构造规划提示模板：系统提示 + 历史对话 + 当前问题 + 检索记忆 + 真实数据
        self._planner_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", PLANNER_AGENT_PROMPT),
                MessagesPlaceholder("history"),
                (
                    "system",
                    (
                        "以下是与当前用户和目的地相关的历史记忆与知识，请在规划时充分利用，"
                        "偏好和以往反馈要优先考虑：\n{memory_context}"
                    ),
                ),
                (
                    "system",
                    (
                        "以下是后端服务返回的真实数据（已经为你准备好，无需再调用工具）：\n"
                        "【景点数据】\n{attraction_data}\n\n"
                        "【天气数据】\n{weather_data}\n\n"
                        "【酒店数据】\n{hotel_data}\n"
                    ),
                ),
                (
                    "human",
                    (
                        "用户旅行需求：\n"
                        "- 目的地：{destination}\n"
                        "- 出行时间：{start_date} 至 {end_date}\n"
                        "- 预算：{budget}\n"
                        "- 旅行偏好：{preferences}\n"
                        "- 酒店偏好：{hotel_preferences}\n\n"
                        "请根据上述信息生成完整的行程 JSON。"
                    ),
                ),
            ]
        )

        # 核心链：组装输入 -> prompt -> LLM
        def _build_chain():
            llm = _get_llm()

            def _enrich_with_memory(inputs: dict) -> dict:
                """
                使用 VectorMemoryService 混合检索用户记忆 + 目的地知识，
                生成 memory_context 文本（供 prompt 使用）。
                """
                user_id: str = inputs.get("user_id") or "anonymous"
                destination: str = inputs.get("destination") or ""
                prefs: list[str] = inputs.get("preferences_list") or []
                query = f"{destination} {' '.join(prefs)}".strip() or destination

                memory_result = vector_memory_service.hybrid_search(
                    user_id=user_id,
                    query=query,
                    user_limit=5,
                    knowledge_limit=5,
                    include_user_memories=True,
                    include_knowledge_memories=True,
                )

                parts: list[str] = []

                user_mems = memory_result.get("user_memories") or []
                if user_mems:
                    texts = [
                        str(m.get("text_representation", ""))[:120] for m in user_mems
                    ]
                    parts.append("用户历史记忆：\n- " + "\n- ".join(texts))

                knowledge_mems = memory_result.get("knowledge_memories") or []
                if knowledge_mems:
                    texts = [
                        str(m.get("text_representation", ""))[:120]
                        for m in knowledge_mems
                    ]
                    parts.append("目的地/经验知识：\n- " + "\n- ".join(texts))

                inputs["memory_context"] = "\n\n".join(parts) if parts else "（暂无可用记忆）"            
                return inputs

            # 把用户输入透传 + memory_context 拼好之后送入 prompt
            base_chain = (
                RunnablePassthrough()
                | _enrich_with_memory
                | self._planner_prompt
                | llm
            )

            return base_chain

        # 构建基础链
        self._base_chain = _build_chain()

        # 封装为带对话记忆的 RunnableWithMessageHistory
        # 注意：RunnableWithMessageHistory 期望的回调签名是 (session_id: str) -> BaseChatMessageHistory
        def _get_history(session_id: str) -> InMemoryChatMessageHistory:
            session_id = session_id or "anonymous"
            if session_id not in self._histories:
                self._histories[session_id] = InMemoryChatMessageHistory()
            return self._histories[session_id]

        self._planner_agent = RunnableWithMessageHistory(
            self._base_chain,
            _get_history,
            input_messages_key="input",    # 我们在调用时会塞一个 "input" 字段作为当前轮自然语言
            history_messages_key="history",
        )

    async def plan_trip_async(self, request: TripPlanRequest) -> TripPlanResponse:
        """
        与原有签名保持一致：输入 TripPlanRequest，返回 TripPlanResponse。
        内部流程：
        1. 调用后端服务获取景点 / 天气 / 酒店真实数据；
        2. 调用带向量记忆 + 对话记忆的规划链生成 JSON；
        3. 解析 JSON -> TripPlanResponse，并为景点补充图片。
        """
        city = request.destination
        days = _trip_days(request)
        prefs_str = ", ".join(request.preferences) if request.preferences else "无"
        hotel_pref_str = (
            ", ".join(request.hotel_preferences) if request.hotel_preferences else "无"
        )
        budget_val = _budget_to_float(request.budget)

        # 1. 直接调用后端服务获取真实数据（替代原来的子专家 + 工具消息抽取）
        try:
            attractions = search_attractions_service(city, days, prefs_str)
            attraction_data = json.dumps(
                [a.model_dump() for a in attractions], ensure_ascii=False
            )
        except Exception as e:
            logger.warning("搜索景点失败: %s", e)
            attraction_data = ""

        try:
            # 在异步上下文中使用异步版天气查询，避免 asyncio.run 触发 RuntimeError
            weather = await get_weather_forecast_service_async(city)
            weather_data = json.dumps(weather.model_dump(), ensure_ascii=False)
        except Exception as e:
            logger.warning("查询天气失败: %s", e)
            weather_data = ""

        try:
            hotels = recommend_hotels_service(city, budget_val, hotel_pref_str)
            hotel_data = json.dumps(
                [h.model_dump() for h in hotels], ensure_ascii=False
            )
        except Exception as e:
            logger.warning("推荐酒店失败: %s", e)
            hotel_data = ""

        logger.info(
            "后端服务调用完成: 景点=%s 条, 天气=%s 字, 酒店=%s 条",
            len(json.loads(attraction_data)) if attraction_data else 0,
            len(weather_data),
            len(json.loads(hotel_data)) if hotel_data else 0,
        )

        # 2. 调用带向量记忆 + 历史记忆的规划链
        # 这里的 session_id 可以按你的需求用 user_id / request 里的某个字段
        session_id = request.user_id if hasattr(request, "user_id") else "anonymous"

        planner_input = {
            # 给 RunnableWithMessageHistory 的「当前轮自然语言输入」
            "input": f"请为用户规划 {city} {days} 天行程。",
            # 供 prompt / memory 检索使用的结构化字段
            "destination": city,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "budget": request.budget,
            "preferences": prefs_str,
            "preferences_list": request.preferences,
            "hotel_preferences": hotel_pref_str,
            "user_id": session_id,
            "attraction_data": attraction_data or "（暂无景点数据）",
            "weather_data": weather_data or "（暂无天气数据）",
            "hotel_data": hotel_data or "（暂无酒店数据）",
        }

        t0 = time.perf_counter()
        try:
            ai_msg = await self._planner_agent.ainvoke(
                planner_input,
                config={"configurable": {"session_id": session_id}},
            )
        finally:
            elapsed = time.perf_counter() - t0
            logger.info("规划 Agent（记忆版）调用完成, 耗时=%.1f 秒", elapsed)

        planner_text = getattr(ai_msg, "content", str(ai_msg))
        data = _parse_planner_json(planner_text)
        if not data:
            logger.warning("规划 Agent（记忆版）未返回有效 JSON，返回基础 TripPlanResponse")
            return TripPlanResponse(
                trip_title=f"{request.destination} 行程规划",
                total_budget=BudgetBreakdown(
                    transport_cost=0.0,
                    dining_cost=0.0,
                    hotel_cost=0.0,
                    attraction_ticket_cost=0.0,
                    total=0.0,
                ),
                hotels=[],
                days=[
                    DailyPlan(
                        day=1,
                        theme="行程生成中",
                        weather=None,
                        recommended_hotel=None,
                        attractions=[],
                        dinings=[],
                        budget=DailyBudget(
                            transport_cost=0.0,
                            dining_cost=0.0,
                            hotel_cost=0.0,
                            attraction_ticket_cost=0.0,
                            total=0.0,
                        ),
                    )
                ],
            )

        # 3. 解析 JSON -> TripPlanResponse，并为景点补图（沿用你原来的逻辑）
        resp = _planner_json_to_trip_plan_response(request, data)
        resp = _enrich_trip_images(request, resp)

        # 4. 将本次行程与偏好写入向量记忆库，便于后续检索与个性化规划
        try:
            user_id_for_memory = session_id or "anonymous"

            # 4.1 记录本次行程结果，用于「相似行程」召回
            trip_record: dict[str, Any] = {
                "destination": request.destination,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "preferences": request.preferences,
                "hotel_preferences": request.hotel_preferences,
                "budget": request.budget,
                "trip_title": resp.trip_title,
                "total_budget": resp.total_budget.model_dump(),
                "days": [
                    {
                        "day": d.day,
                        "theme": d.theme,
                        "attractions": [a.model_dump() for a in d.attractions],
                    }
                    for d in resp.days
                ],
            }
            vector_memory_service.store_user_trip(
                user_id=user_id_for_memory,
                trip_data=trip_record,
            )

            # 4.2 记录本次请求的偏好摘要，用于「用户偏好」召回
            preference_record: dict[str, Any] = {
                "destination": request.destination,
                "preferences": request.preferences,
                "hotel_preferences": request.hotel_preferences,
                "budget": request.budget,
            }
            vector_memory_service.store_user_preference(
                user_id=user_id_for_memory,
                preference_type="trip_request",
                preference_data=preference_record,
            )

            # 4.3 持久化向量索引到磁盘
            vector_memory_service.save()
        except Exception as e:
            # 向量记忆写入失败不能影响主流程，仅打日志
            logger.warning("写入向量记忆失败，将跳过本次记忆: %s", e)

        return resp