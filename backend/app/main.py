from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.v1 import trip_routes, health_routes, user_routes, auth_routes
from .middleware.auth import AuthMiddleware
from .observability.logger import setup_logger
from .middleware.request_id import RequestIDMiddleware
from .middleware.rate_limit import RateLimitMiddleware, RateLimiter
from .exceptions.exception_handler import global_exception_handler


from pathlib import Path

def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。
    """
    # 启动时初始化日志：配置 root logger，接住所有 logging.getLogger(__name__) 的日志
    setup_logger(name="", log_level=getattr(settings, "LOG_LEVEL", "INFO"))

    app = FastAPI(
        title="Trip Planner API",
        description="基于 LangChain 的智能旅行规划后端服务",
        version="0.1.0",
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载认证中间件，用于解析 JWT 并设置 request.state.user
    # 配置中间件（注意顺序很重要）
    # 1. 请求ID中间件（最外层，最先执行）
    app.add_middleware(RequestIDMiddleware)

    # 2. 认证中间件（在限流之前，以便统计用户请求）
    app.add_middleware(AuthMiddleware,
                    jwt_secret=settings.JWT_SECRET,
                    jwt_expiry_hours=settings.JWT_EXPIRY_HOURS)

    # 3. 限流中间件
    rate_limiter = RateLimiter(
        global_rate=100,  # 全局：100个请求/秒
        per_ip_rate=20,   # 每个IP：20个请求/秒
        enabled=True
    )
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

    # 4. CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


    # 注册异常处理器
    app.add_exception_handler(Exception, global_exception_handler)

    # 挂载静态文件服务（用于头像等文件）
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


    register_routes(app)  # 注册路由
    # 前端健康检查使用 GET /health（无前缀）
    @app.get("/health", summary="健康检查（根路径）")
    async def root_health() -> dict:
        return {"status": "ok"}

    return app

def register_routes(app: FastAPI):
    """
    注册路由
    """
    app.include_router(trip_routes.router, prefix="/api/v1/trips")
    app.include_router(health_routes.router, prefix="/api/v1/health")
    app.include_router(user_routes.router, prefix="/api/v1/user")
    app.include_router(auth_routes.router, prefix="/api/v1/auth")


app = create_app()
