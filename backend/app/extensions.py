"""
FastAPI 扩展模块，用于初始化 Redis 连接、数据库连接、向量库连接等。
"""

from fastapi import FastAPI
from redis import Redis  # pyright: ignore[reportMissingImports]
from .config import settings

def init_redis(app: FastAPI):
    """
    初始化 Redis 连接
    """
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )

    return redis_client

# def init_database(app: FastAPI):

# def init_vector_database(app: FastAPI):