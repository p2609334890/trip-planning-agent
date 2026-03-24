"""
"""
import json
import re
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Annotated, Any, Optional

import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import create_react_agent
from typing_extensions import NotRequired, TypedDict

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
from app.agents.tools.agent_tool import (
    get_weather,
    recommend_hotels,
    search_attractions,
)

from app.services.retrieval_service import vector_memory_service  # 复用向量记忆
# ============ Agent提示词 ============


PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息、酒店信息和天气信息，生成详细的旅行计划。

**RAG 外部知识（向量记忆检索）:**
- 提示词中会注入「用户历史记忆」与「目的地/旅行经验知识」，来自向量库的语义检索，用于补充常识、季节与节奏建议。
- 这些片段**不替代工具返回的真实数据**：景点列表、坐标、天气、酒店等**必须通过工具查询得到**；若常识与工具数据冲突，**以工具数据为准**。禁止编造未出现在工具结果中的景点/酒店/天气。

**工具使用（必须先调用工具）:**
1. `search_attractions(city, days, preferences)`：根据目的地城市、行程天数、偏好字符串（可用逗号分隔多个关键词）搜索景点候选。
2. `get_weather(city)`：查询目的地城市的天气（用于行程中的 weather 字段）。
3. `recommend_hotels(city, budget, location_pref)`：根据城市、预算数值（人民币元，浮点数）、位置/酒店偏好字符串推荐酒店。
在输出最终 JSON 行程之前，**请至少各调用一次**上述工具（若某工具失败可在最终说明中简要体现，但仍不得凭空捏造 POI）。

**重要提示:**
1. 你应该参考用户的历史行程和反馈来优化规划策略
2. 规划所选景点、酒店应来自工具返回结果；可对工具结果做筛选与排序，但不得引入工具未返回的地点
3. 若工具返回信息不足，可再次调用工具或调整参数，不要编造数据
4. 生成最终答案时，只输出符合要求的 JSON，不要输出其它解释文字

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


class TripPlannerState(TypedDict):
    """LangGraph ReAct 规划 Agent 状态：消息 + 可选记忆上下文。"""

    messages: Annotated[Sequence[AnyMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]
    memory_context: NotRequired[str]


def _trip_planner_prompt(state: TripPlannerState):
    """将系统提示、向量记忆与用户/工具消息一并交给模型。"""
    mem = state.get("memory_context") or "（暂无可用记忆）"
    system_content = PLANNER_AGENT_PROMPT + "\n\n**当前轮次的向量记忆参考：**\n" + mem
    return [SystemMessage(content=system_content)] + list(state["messages"])


# 进程内共享 checkpointer，使同一 thread_id（如 user_id）在多请求间保留对话历史
_TRIP_PLANNER_CHECKPOINTER = MemorySaver()
_TRIP_PLANNER_GRAPH: Any = None


def _get_or_create_trip_planner_graph():
    """懒加载 LangGraph 预置 ReAct Agent（绑定景点/天气/酒店工具）。"""
    global _TRIP_PLANNER_GRAPH
    if _TRIP_PLANNER_GRAPH is None:
        _TRIP_PLANNER_GRAPH = create_react_agent(
            _get_llm(),
            tools=[search_attractions, get_weather, recommend_hotels],
            prompt=_trip_planner_prompt,
            state_schema=TripPlannerState,
            checkpointer=_TRIP_PLANNER_CHECKPOINTER,
            version="v2",
            name="trip_planner",
        )
    return _TRIP_PLANNER_GRAPH


def _build_memory_context_for_request(request: TripPlanRequest) -> str:
    """混合检索用户记忆 + 目的地知识，供规划系统提示使用。"""
    user_id = getattr(request, "user_id", None) or "anonymous"
    destination = (request.destination or "").strip()
    prefs: list[str] = list(request.preferences or [])
    query = f"{destination} {' '.join(prefs)}".strip() or destination

    memory_result = vector_memory_service.hybrid_search(
        user_id=user_id,
        query=query,
        user_limit=5,
        knowledge_limit=6,
        include_user_memories=True,
        include_knowledge_memories=True,
    )

    def _clip_text(s: str, max_len: int) -> str:
        s = (s or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"

    parts: list[str] = []

    user_mems = memory_result.get("user_memories") or []
    if user_mems:
        texts = [
            _clip_text(str(m.get("text_representation", "")), 220)
            for m in user_mems
        ]
        parts.append("用户历史记忆：\n- " + "\n- ".join(texts))

    knowledge_mems = memory_result.get("knowledge_memories") or []
    if knowledge_mems:
        texts = [
            _clip_text(str(m.get("text_representation", "")), 720)
            for m in knowledge_mems
        ]
        parts.append("目的地/经验知识（RAG 检索）：\n- " + "\n- ".join(texts))

    return "\n\n".join(parts) if parts else "（暂无可用记忆）"


def _ai_message_text_content(msg: AIMessage) -> str:
    """统一解析 AIMessage.content（字符串或多段 content block）。"""
    c = getattr(msg, "content", None)
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if t:
                    parts.append(str(t))
        return "".join(parts)
    return str(c)


def _extract_planner_text_from_messages(messages: Sequence[AnyMessage]) -> str:
    """从 ReAct 结束后的消息列表中提取最终规划 JSON 文本。"""
    for m in reversed(list(messages)):
        if not isinstance(m, AIMessage):
            continue
        tool_calls = getattr(m, "tool_calls", None) or []
        if tool_calls:
            continue
        text = _ai_message_text_content(m).strip()
        if text:
            return text
    for m in reversed(list(messages)):
        if isinstance(m, AIMessage):
            text = _ai_message_text_content(m).strip()
            if text:
                return text
    return ""


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


#"""行程规划 Agent：LangGraph 预置 ReAct + 工具调用，生成最终行程。"""

class TripPlannerAgent:
    """
    旅行规划 Agent（LangGraph create_react_agent + 向量记忆）：
    - 通过工具 `search_attractions` / `get_weather` / `recommend_hotels` 获取真实数据；
    - 使用 VectorMemoryService 检索记忆，经 `memory_context` 注入系统提示；
    - 使用 LangGraph MemorySaver + thread_id 维护多轮对话；
    - 输出 TripPlanResponse，接口与原来保持一致。
    """

    def __init__(self) -> None:
        self._graph = _get_or_create_trip_planner_graph()

    async def plan_trip_async(self, request: TripPlanRequest) -> TripPlanResponse:
        """
        与原有签名保持一致：输入 TripPlanRequest，返回 TripPlanResponse。
        内部流程：
        1. 检索向量记忆，写入 memory_context；
        2. LangGraph ReAct：模型按需调用工具获取景点/天气/酒店；
        3. 解析最终 JSON -> TripPlanResponse，并为景点补充图片。
        """
        city = request.destination
        days = _trip_days(request)
        prefs_str = ", ".join(request.preferences) if request.preferences else "无"
        hotel_pref_str = (
            ", ".join(request.hotel_preferences) if request.hotel_preferences else "无"
        )
        budget_val = _budget_to_float(request.budget)

        memory_context = _build_memory_context_for_request(request)

        session_id = getattr(request, "user_id", None) or "anonymous"
        thread_id = str(session_id)

        user_content = (
            "请为用户规划行程，先使用工具获取景点、天气与酒店数据，再输出完整行程 JSON。\n\n"
            f"- 目的地（city）：{city}\n"
            f"- 行程天数（days）：{days}\n"
            f"- 出行时间：{request.start_date} 至 {request.end_date}\n"
            f"- 预算档位描述：{request.budget}（规划酒店工具时请使用数值 budget={budget_val} 元人民币）\n"
            f"- 旅行偏好（preferences 字符串）：{prefs_str}\n"
            f"- 酒店偏好（location_pref）：{hotel_pref_str}\n"
        )

        graph_input: TripPlannerState = {
            "messages": [HumanMessage(content=user_content)],
            "memory_context": memory_context,
        }

        t0 = time.perf_counter()
        try:
            result = await self._graph.ainvoke(
                graph_input,
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 50,
                },
            )
        finally:
            elapsed = time.perf_counter() - t0
            logger.info("规划 Agent（LangGraph ReAct）调用完成, 耗时=%.1f 秒", elapsed)

        messages_out = result.get("messages") or []
        planner_text = _extract_planner_text_from_messages(messages_out)
        data = _parse_planner_json(planner_text)
        if not data:
            logger.warning("规划 Agent（LangGraph ReAct）未返回有效 JSON，返回基础 TripPlanResponse")
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