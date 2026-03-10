"""
日志封装：统一 get_logger，便于后续接入链路追踪/指标。
"""

import logging
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 logger。若未指定 name，返回根 logger。
    """
    return logging.getLogger(name or __name__)
