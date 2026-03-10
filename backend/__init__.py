"""
backend 包初始化，使 FastAPI 后端可通过 mytrip.backend 导入。
"""

# 本包用于初始化 mytrip.backend，使其作为可导入包存在。
# 通常不在此文件中放置业务逻辑。
# 可按需要在此处声明 __all__，例：
# __all__ = ["settings", "create_app"]

__all__ = ["settings", "create_app"]