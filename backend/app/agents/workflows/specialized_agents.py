"""
专业智能体实现：多 Agent 架构
- 旅行规划主 Agent：收集 3 个子专家结果，生成最终行程
- 子专家：景点搜索专家、天气查询专家、酒店推荐专家

设计说明：规划 Agent 统筹期间直接使用 subagent 返回的信息是合理的。
现实旅行需考虑天气、住宿、景点等条件，由各 subagent 分别调用真实能力（API），
规划 Agent 只做汇总与排期，避免重复调用、保证信息一致，且职责清晰。
为提升准确性，传入规划 Agent 的优先为子专家工具调用的真实返回（结构化数据），
其次才是子专家的自然语言总结。
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
from app.models.trip_plan import TripPlan, DayItinerary, MapPoint, BudgetSummary
from app.agents.tools import agent_tool
from app.services.agent_sercvice import recommend_hotels as recommend_hotels_service


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

**响应格式（示例，仅作为结构参考，字段名和类型必须严格遵守）：**
```json
{
  "trip_title": "一个吸引人的行程标题",
  "total_budget": {
    "transport_cost": 300.0,
    "dining_cost": 800.0,
    "hotel_cost": 1200.0,
    "attraction_ticket_cost": 400.0,
    "total": 2700.0
  },
  "hotels": [
    {
      "name": "酒店名称",
      "address": "酒店地址",
      "location": {"lat": 39.915, "lng": 116.397},
      "price": "400元/晚",
      "rating": "4.5",
      "distance_to_main_attraction_km": 1.2
    }
  ],
  "days": [
    {
      "day": 1,
      "theme": "古都历史探索",
      "weather": {
        "date": "YYYY-MM-DD",
        "day_weather": "晴",
        "night_weather": "多云",
        "day_temp": "25",
        "night_temp": "15",
        "day_wind": "东风3级",
        "night_wind": "西北风2级"
      },
      "recommended_hotel": {
        "name": "当日推荐酒店",
        "address": "酒店地址",
        "location": {"lat": 39.915, "lng": 116.397},
        "price": "400元/晚",
        "rating": "4.5",
        "distance_to_main_attraction_km": 0.8
      },
      "attractions": [
        {
          "name": "景点名称",
          "type": "历史文化",
          "rating": "4.7",
          "suggested_duration_hours": 3.0,
          "description": "景点简介和游览建议",
          "address": "景点地址",
          "location": {"lat": 39.915, "lng": 116.397},
          "image_urls": [
            "https://example.com/attraction-image-1.jpg"
          ],
          "ticket_price": "60"
        }
      ],
      "dinings": [
        {
          "name": "餐厅名称",
          "address": "餐厅地址",
          "location": {"lat": 39.910, "lng": 116.400},
          "cost_per_person": "80",
          "rating": "4.5"
        }
      ],
      "budget": {
        "transport_cost": 50.0,
        "dining_cost": 200.0,
        "hotel_cost": 400.0,
        "attraction_ticket_cost": 120.0,
        "total": 770.0
      }
    }
  ]
}
```

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
UNSPLASH_API_URL = "https://api.unsplash.com"


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


# ---------- 子专家 Agent 图（创建一次，复用）----------
#"""景点搜索专家：仅使用 search_attractions 工具。"""
def _create_attraction_expert():
    """景点搜索专家：仅使用 search_attractions 工具。"""
    return create_agent(
        model=_get_llm(),
        tools=[agent_tool.search_attractions],
        system_prompt=ATTRACTION_AGENT_PROMPT,
        name="attraction_expert",
    )


#"""天气查询专家：仅使用 get_weather 工具。"""
def _create_weather_expert():
    """天气查询专家：仅使用 get_weather 工具。"""
    return create_agent(
        model=_get_llm(),
        tools=[agent_tool.get_weather],
        system_prompt=WEATHER_AGENT_PROMPT,
        name="weather_expert",
    )


#"""酒店推荐专家：仅使用 recommend_hotels 工具。"""
def _create_hotel_expert():
    """酒店推荐专家：仅使用 recommend_hotels 工具。"""
    return create_agent(
        model=_get_llm(),
        tools=[agent_tool.recommend_hotels],
        system_prompt=HOTEL_AGENT_PROMPT,
        name="hotel_expert",
    )


#"""行程规划 Agent：无工具，仅根据子专家结果生成最终 JSON 行程。"""
def _create_planner_agent():
    """行程规划 Agent：无工具，仅根据子专家结果生成最终 JSON 行程。"""
    return create_agent(
        model=_get_llm(),
        tools=[],  # 规划器不调用工具，只做汇总与生成
        system_prompt=PLANNER_AGENT_PROMPT,
        name="trip_planner",
    )


# 懒加载单例，避免重复构建图
_attraction_expert = None
_weather_expert = None
_hotel_expert = None
_planner_agent = None

#"""获取景点搜索专家实例。"""
def _get_attraction_expert():
    global _attraction_expert
    if _attraction_expert is None:
        _attraction_expert = _create_attraction_expert()
    return _attraction_expert


#"""获取天气查询专家实例。"""
def _get_weather_expert():
    global _weather_expert
    if _weather_expert is None:
        _weather_expert = _create_weather_expert()
    return _weather_expert


#"""获取酒店推荐专家实例。"""
def _get_hotel_expert():
    global _hotel_expert
    if _hotel_expert is None:
        _hotel_expert = _create_hotel_expert()
    return _hotel_expert


#"""获取行程规划 Agent 实例。"""
def _get_planner_agent():
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = _create_planner_agent()
    return _planner_agent


#"""从 agent 返回的 state 中取出最后一条 AI 消息的文本。"""
def _extract_final_text(state: dict) -> str:
    """从 agent 返回的 state 中取出最后一条 AI 消息的文本。"""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and isinstance(content, str) and content.strip():
            return content
    return ""


#"""从子专家 state 中提取工具调用的真实返回（ToolMessage.content）。"""
def _extract_tool_results(state: dict) -> str:
    """
    从子专家 state 中提取工具调用的真实返回（ToolMessage.content）。
    规划 Agent 直接使用这些结构化数据是合理的：子专家负责调用天气/住宿/景点等
    真实能力，规划 Agent 只做统筹与排期，避免重复调用 API 且信息一致。
    若有多次工具调用，则拼接所有工具返回。
    """
    messages = state.get("messages", [])
    parts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = getattr(msg, "content", None)
            if content is None:
                continue
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        parts.append(json.dumps(item, ensure_ascii=False))
                    elif isinstance(item, str) and item.strip():
                        parts.append(item.strip())
    return "\n".join(parts) if parts else ""


#"""异步执行子专家 Agent。"""
async def _run_subagent(graph, user_content: str) -> dict:
    """
    异步执行子专家 Agent。
    返回 {"state": state, "tool_results": str, "final_text": str}，
    便于规划 Agent 优先使用 tool_results（真实工具返回），无工具结果时用 final_text。
    """
    try:
        state = await graph.ainvoke({"messages": [HumanMessage(content=user_content)]})
        tool_results = _extract_tool_results(state)
        final_text = _extract_final_text(state)
        return {"state": state, "tool_results": tool_results, "final_text": final_text}
    except Exception as e:
        logger.warning("子专家执行异常: %s", e)
        return {"state": None, "tool_results": "", "final_text": ""}


#"""组装给规划 Agent 的用户消息：用户需求 + 三个子专家返回的信息。"""
def _build_planner_user_message(
    request: TripPlanRequest,
    attraction_data: str,
    weather_data: str,
    hotel_data: str,
) -> str:
    """
    组装给规划 Agent 的用户消息：用户需求 + 三个子专家返回的信息。
    此处传入的应是「子专家工具调用的真实返回」（优先）或子专家总结文本，
    以便规划 Agent 直接基于真实数据统筹，而不是基于二次转述。
    """
    return (
        "请根据以下用户需求与各子专家返回的**真实数据**，生成一份完整的旅行计划 JSON。"
        "规划时请直接使用下方景点、天气、酒店的具体信息（名称、地址、坐标、价格等），不要编造。\n\n"
        f"【用户需求】\n"
        f"- 目的地：{request.destination}\n"
        f"- 出行时间：{request.start_date} 至 {request.end_date}\n"
        f"- 预算：{request.budget}\n"
        f"- 旅行偏好：{', '.join(request.preferences) or '无'}\n"
        f"- 酒店偏好：{', '.join(request.hotel_preferences) or '无'}\n\n"
        f"【景点搜索专家-工具返回数据】\n{attraction_data or '（暂无）'}\n\n"
        f"【天气查询专家-工具返回数据】\n{weather_data or '（暂无）'}\n\n"
        f"【酒店推荐专家-工具返回数据】\n{hotel_data or '（暂无）'}\n\n"
        "请严格按照系统提示中的 JSON 结构输出行程计划，不要添加额外说明。"
    )


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
def _planner_json_to_trip_plan(
    request: TripPlanRequest, data: dict[str, Any]
) -> TripPlan:
    """将规划 Agent 输出的 JSON 转为 TripPlan 模型。"""
    title = data.get("trip_title") or f"{request.destination} 行程规划"
    total_budget = data.get("total_budget") or {}
    total = total_budget.get("total")
    budget_summary = None
    if total is not None:
        budget_summary = BudgetSummary(
            total=float(total),
            accommodation=total_budget.get("hotel_cost"),
            transport=total_budget.get("transport_cost"),
            tickets=total_budget.get("attraction_ticket_cost"),
            food=total_budget.get("dining_cost"),
            other=None,
        )

    days_data = data.get("days") or []
    days: list[DayItinerary] = []
    for d in days_data:
        day_num = d.get("day", len(days) + 1)
        theme = d.get("theme") or f"第{day_num}天"
        attractions = d.get("attractions") or []
        dinings = d.get("dinings") or []
        items = []
        for a in attractions:
            name = a.get("name", "")
            desc = a.get("description", "")
            items.append({"content": f"景点：{name} — {desc}"})
        for din in dinings:
            name = din.get("name", "")
            cost = din.get("cost_per_person", "")
            items.append({"content": f"餐饮：{name}（人均约 {cost} 元）"})
        if not items:
            items = [{"content": theme}]

        map_points: list[MapPoint] = []
        for a in attractions:
            loc = a.get("location") or {}
            if loc.get("lat") is not None and loc.get("lng") is not None:
                map_points.append(
                    MapPoint(
                        name=a.get("name", ""),
                        lat=float(loc["lat"]),
                        lng=float(loc["lng"]),
                        type="attraction",
                    )
                )

        date_val = None
        if day_num <= len(days_data) and request.start_date:
            try:
                base = datetime.strptime(request.start_date, "%Y-%m-%d")
                date_val = (base + timedelta(days=day_num - 1)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        days.append(
            DayItinerary(
                day=day_num,
                date=date_val,
                summary=theme,
                items=items,
                map_points=map_points,
            )
        )

    return TripPlan(
        title=title,
        destination=request.destination,
        days=days,
        budget=budget_summary,
        map_points=[],
        tips=None,
    )


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
        day_num = d.get("day", i + 1)
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


def _fetch_unsplash_image_urls(query: str, per_page: int = 1) -> list[str]:
    """
    根据查询关键词调用 Unsplash 搜索图片。
    返回若干张图片 URL（small/regular）。
    """
    if not settings.UNSPLASH_ACCESS_KEY:
        logger.debug("UNSPLASH_ACCESS_KEY 未配置，跳过图片搜索")
        return []
    try:
        resp = requests.get(
            f"{UNSPLASH_API_URL}/search/photos",
            params={"query": query, "per_page": per_page},
            headers={
                "Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}",
                "Accept-Version": "v1",
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json() or {}
        results = data.get("results") or []
        urls: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            raw_urls = item.get("urls") or {}
            if not isinstance(raw_urls, dict):
                continue
            url = raw_urls.get("small") or raw_urls.get("regular")
            if url:
                urls.append(url)
        return urls
    except Exception as e:
        logger.warning("Unsplash 图片搜索失败 query=%s: %s", query, e)
        return []


def _enrich_trip_images_with_unsplash(
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
    - 若已有图片但不是 Unsplash 来源，尝试使用 Unsplash 替换，避免 404/防盗链
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
            has_valid_unsplash = any(
                isinstance(u, str) and "images.unsplash.com" in u for u in cur_urls
            )

            # 若已有 Unsplash 图片，则不再补充
            if has_valid_unsplash:
                continue

            name = (attraction.name or "").strip()
            if not name:
                continue

            query_parts = [city, name]
            query = " ".join([p for p in query_parts if p])
            if not query:
                continue

            urls = _fetch_unsplash_image_urls(query, per_page=per_attraction)
            if urls:
                # 用 Unsplash 结果覆盖原有非 Unsplash 图片，避免 404/防盗链
                attraction.image_urls = urls
                filled += 1

    return resp


#"""行程规划 Agent：收集 3 个子专家结果，生成最终行程。"""
class TripPlannerAgent:
    """
    多 Agent 旅行规划器：
    - 并行调用景点搜索、天气查询、酒店推荐三个子专家；
    - 将结果汇总给规划 Agent，生成最终行程并解析为 TripPlanResponse（与前端约定一致）。
    """

    async def plan_trip_async(self, request: TripPlanRequest) -> TripPlanResponse:
        days = _trip_days(request)
        city = request.destination
        prefs = ", ".join(request.preferences) if request.preferences else "景点"
        budget_val = _budget_to_float(request.budget)
        hotel_pref = ", ".join(request.hotel_preferences) if request.hotel_preferences else "无"

        # 1. 并行执行三个子专家（各返回 tool_results + final_text）
        attraction_task = _run_subagent(
            _get_attraction_expert(),
            f"请搜索{city}的{prefs}相关景点，行程共{days}天，需要足够景点填充行程。",
        )
        weather_task = _run_subagent(
            _get_weather_expert(),
            f"请查询{city}的天气，行程日期为 {request.start_date} 至 {request.end_date}。",
        )
        hotel_task = _run_subagent(
            _get_hotel_expert(),
            f"请推荐{city}的酒店，预算约{budget_val}元/晚，偏好：{hotel_pref}。",
        )

        out_attr, out_weather, out_hotel = await asyncio.gather(
            attraction_task, weather_task, hotel_task
        )

        # 规划 Agent 直接使用子专家结果：优先用工具真实返回（结构化），无则用其总结文本
        def _prefer_tool_result(out: dict) -> str:
            return (out.get("tool_results") or "").strip() or (out.get("final_text") or "").strip()

        attraction_data = _prefer_tool_result(out_attr)
        weather_data = _prefer_tool_result(out_weather)
        hotel_data = _prefer_tool_result(out_hotel)

        # 如果酒店子专家因为内容策略等原因失败（state 为空且无 tool_results），
        # 直接调用后端酒店服务作为兜底，避免整个规划失败。
        if (not hotel_data) and (out_hotel.get("state") is None):
            try:
                fallback_hotels = recommend_hotels_service(
                    city=city,
                    budget=budget_val,
                    location_pref=hotel_pref,
                )
                hotel_data = json.dumps(
                    [h.model_dump() for h in fallback_hotels], ensure_ascii=False
                )
                logger.warning(
                    "酒店子专家失败，已使用 recommend_hotels_service 结果兜底，数量=%s",
                    len(fallback_hotels),
                )
            except Exception as e:
                logger.warning("酒店兜底 recommend_hotels_service 调用失败: %s", e)

        logger.info(
            "子专家完成: 景点=%s 字, 天气=%s 字, 酒店=%s 字（优先使用工具返回）",
            len(attraction_data),
            len(weather_data),
            len(hotel_data),
        )

        # 2. 规划 Agent 基于上述真实数据统筹并生成 JSON
        planner_msg = _build_planner_user_message(
            request, attraction_data, weather_data, hotel_data
        )
        planner_graph = _get_planner_agent()
        t0 = time.perf_counter()
        try:
            planner_state = await planner_graph.ainvoke(
                {"messages": [HumanMessage(content=planner_msg)]}
            )
        finally:
            elapsed = time.perf_counter() - t0
            logger.info("规划 Agent 调用完成, 耗时=%.1f 秒", elapsed)
        planner_text = _extract_final_text(planner_state)

        # 3. 解析 JSON 并转为 TripPlanResponse（与前端约定一致）
        data = _parse_planner_json(planner_text)
        if not data:
            logger.warning("规划 Agent 未返回有效 JSON，返回基础 TripPlanResponse")
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
        resp = _planner_json_to_trip_plan_response(request, data)
        # 在行程规划完成后，再为部分景点补充图片信息
        resp = _enrich_trip_images_with_unsplash(request, resp)
        return resp
