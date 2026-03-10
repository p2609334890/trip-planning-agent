"""
封装 LLM 调用：统一模型、超时与重试。
（先用最简单版本：单轮调用；后续可接入 LangChain ChatModel。）
"""

from typing import Optional
from app.config import settings


class LLMService:
    """LLM 服务：封装大模型调用。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL_ID
        self.timeout = timeout or getattr(settings, "LLM_TIMEOUT", 100)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        单轮生成文本。后续可改为 LangChain ChatModel.invoke。
        """
        # TODO: 接入真实 LLM（OpenAI 兼容 API / 智谱 / 其他）
        # 骨架：先返回占位，避免未实现时报错
        return f"[LLM 占位] 收到 prompt 长度: {len(prompt)}，模型: {self.model}"

    async def generate_itinerary(self, user_input: str, system_prompt: Optional[str] = None) -> str:
        """
        根据用户输入与可选系统提示词，生成行程相关文本。
        """
        full_prompt = (system_prompt or "") + "\n\n" + user_input
        return await self.generate(full_prompt)


def get_llm_service() -> LLMService:
    """依赖注入用：获取 LLM 服务实例。"""
    return LLMService()
