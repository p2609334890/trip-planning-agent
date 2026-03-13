from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类，用于加载和管理环境变量。
    使用 Pydantic BaseSettings 自动从环境变量 / .env 中解析配置。
    """

    # ========= LLM 配置 =========
    # 必填：不配置会在启动时报错，方便尽早发现问题
    LLM_MODEL_ID: str
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_TIMEOUT: int = 100  # 默认超时时间（秒）

    # 特定服务商的 API Keys（用于自动检测，可选）
    OPENAI_API_KEY: Optional[str] = None
    ZHIPU_API_KEY: Optional[str] = None
    MODELSCOPE_API_KEY: Optional[str] = None

    # ========= 服务器配置 =========
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ========= CORS 配置 =========
    # 逗号分隔的域名列表
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ========= 日志配置 =========
    LOG_LEVEL: str = "INFO"

    # ========= Unsplash API =========
    UNSPLASH_ACCESS_KEY: Optional[str] = None
    UNSPLASH_SECRET_KEY: Optional[str] = None
    # ========= 图片服务（Pexels）API =========
    # 若需要切换为其他图片服务，只需在 .env 中调整对应的 KEY / URL，
    # 以及在使用处更换调用逻辑即可。
    PEXELS_API_KEY: Optional[str] = "ucy6Rfp279kgn0yXLjy2nLjPJMJsnELejgzjWhfV735zG3rA15RTkv0G"
    # 允许通过环境变量覆盖默认 Pexels 接口地址
    PEXELS_API_URL: str = "https://api.pexels.com"

    # ========= 高德地图 API =========
    # 必填：需要在环境变量或 .env 中配置
    AMAP_API_KEY: str

    #  MCP Server
    TRAVEL_MCP_SERVER_TYPE: str = "stdio"
    CAIYUN_API_KEY: str = "BdU7d6sSXtJVkkEi"
    TRAVEL_MCP_ALLOWED_TOOLS: str = "get_weather_by_address"

    # ========= JWT 认证配置 =========
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_EXPIRY_HOURS: int = 24

    # ========= Redis 配置 =========
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DECODE_RESPONSES: bool = True

    # ========= 密码加密配置 =========
    BCRYPT_ROUNDS: int = 12

    # ========= 向量数据库 / 嵌入模型配置 =========
    VECTOR_MEMORY_DIR: str = "vector_memory"
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_DIM: int = 384

    # ========= HuggingFace 配置 =========
    HF_ENDPOINT: str = "https://hf-mirror.com"
    HF_HUB_OFFLINE: bool = False
    HF_HUB_CACHE_DIR: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_cors_origins_list(self) -> List[str]:
        """获取 CORS origins 列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# 全局配置实例
settings = Settings()