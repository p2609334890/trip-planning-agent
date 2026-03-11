from pydantic import BaseModel
from typing import Callable

class Tools(BaseModel):
    name: str
    description: str
    func: Callable

class Tools:
    def __init__(self):
        self.tools = []

    def register_tool(self, tool: Tools):
        self.tools.append(tool)

    def execute_tool(self, name: str, *args, **kwargs):
        return self.tools

# mytrip/backend/app/services/tools.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.services.agent_sercvice import (
    search_attractions,
    recommend_hotels,
    get_weather_forecast,
    estimate_budget,
    plan_route,
)


@dataclass
class Tool:
    """
    通用工具抽象：把一个 Python 函数包装成 Agent 可调用的 Tool。
    """
    name: str
    description: str
    func: Callable[..., Any]

    def run(self, params: Dict[str, Any]) -> Any:
        """
        统一的调用入口。
        - params 是从 Agent/LLM 解析出来的参数字典
        - 内部直接用 **params 调用底层业务函数
        """
        return self.func(**params)


class ToolRegistry:
    """
    简单工具注册表：
    - 负责保存 name -> Tool 的映射
    - 对外提供 execute_tool / get_tool / list_tools 等方法
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> None:
        """
        注册一个工具，如果同名会覆盖。
        """
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def execute_tool(self, name: str, **params: Any) -> Any:
        """
        通过名称执行工具。
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"未找到名为 '{name}' 的工具")
        return tool.run(params)

    def list_tools(self) -> list[str]:
        """
        返回当前所有已注册工具的名称列表，方便在 system prompt 里展示。
        """
        return list(self._tools.keys())

    def get_tools_description(self) -> str:
        """
        生成一个简单的工具描述文本，后续可以直接塞进系统提示词里。
        """
        if not self._tools:
            return "暂无可用工具"

        lines: list[str] = []
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)


# --------- 工具注册（基于现有业务函数） ---------

def create_default_tool_registry() -> ToolRegistry:
    """
    创建一个包含当前所有业务函数的默认 ToolRegistry。
    之后你在 Agent 初始化时可以直接调用这个方法拿到注册好的 registry。
    """
    registry = ToolRegistry()

    registry.register_tool(
        Tool(
            name="search_attractions",
            description="根据城市、天数和偏好搜索景点候选列表。",
            func=search_attractions,
        )
    )

    registry.register_tool(
        Tool(
            name="recommend_hotels",
            description="根据城市、预算和位置偏好推荐酒店列表。",
            func=recommend_hotels,
        )
    )

    registry.register_tool(
        Tool(
            name="get_weather_forecast",
            description="查询指定城市的天气信息。",
            func=get_weather_forecast,
        )
    )

    registry.register_tool(
        Tool(
            name="estimate_budget",
            description="根据行程请求、景点和酒店信息估算整体预算。",
            func=estimate_budget,
        )
    )

    registry.register_tool(
        Tool(
            name="plan_route",
            description="根据一组经纬度点位规划简单路线（polyline 与距离时间估算）。",
            func=plan_route,
        )
    )

    return registry