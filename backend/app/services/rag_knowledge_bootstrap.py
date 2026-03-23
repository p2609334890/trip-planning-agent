"""
将静态旅行知识写入向量记忆（FAISS 知识索引），用于规划链 RAG 召回。
仅在知识库为空时批量灌入，避免重复启动时无限追加。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.knowledge.travel_rag_seed import DESTINATION_KNOWLEDGE_SEED, EXPERIENCE_KNOWLEDGE_SEED
from app.observability.logger import default_logger as logger

if TYPE_CHECKING:
    from app.services.retrieval_service import VectorMemoryService


def bootstrap_travel_knowledge_if_empty(service: "VectorMemoryService") -> int:
    """
    若知识索引尚无条目，则写入种子数据。返回本次新增条数。
    """
    if service.knowledge_memory_index.ntotal > 0:
        logger.info(
            "RAG 知识库已有 %s 条，跳过种子写入",
            service.knowledge_memory_index.ntotal,
        )
        return 0

    n = 0
    for destination, data in DESTINATION_KNOWLEDGE_SEED:
        service.store_destination_knowledge(destination, data)
        n += 1
    for exp_type, data in EXPERIENCE_KNOWLEDGE_SEED:
        service.store_travel_experience(exp_type, data)
        n += 1

    logger.info("RAG 旅行知识种子已写入，共 %s 条", n)
    try:
        service.save()
    except Exception as e:
        logger.warning("RAG 种子写入后保存索引失败（不影响内存检索）: %s", e)
    return n
