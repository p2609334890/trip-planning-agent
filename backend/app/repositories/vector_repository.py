"""
向量知识仓储门面：对外暴露 RAG 读写与检索接口，底层委托 VectorMemoryService（FAISS + 句向量）。
业务代码优先调用本模块，便于日后替换为远程向量库而不改调用方。
"""

from __future__ import annotations

from typing import Any

from app.services.retrieval_service import vector_memory_service


def store_destination_knowledge(destination: str, knowledge_data: dict[str, Any]) -> None:
    """写入目的地相关知识（嵌入后进入知识索引）。"""
    vector_memory_service.store_destination_knowledge(destination, knowledge_data)


def store_travel_experience(experience_type: str, experience_data: dict[str, Any]) -> None:
    """写入通用旅行经验类知识。"""
    vector_memory_service.store_travel_experience(experience_type, experience_data)


def search_knowledge(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """按查询语义检索知识记忆（RAG 核心）。"""
    return vector_memory_service.retrieve_knowledge_memories(query, limit=limit)


def hybrid_rag_context(
    user_id: str,
    query: str,
    *,
    user_limit: int = 5,
    knowledge_limit: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """同时检索用户记忆与外部知识，供规划链组装 prompt。"""
    return vector_memory_service.hybrid_search(
        user_id=user_id,
        query=query,
        user_limit=user_limit,
        knowledge_limit=knowledge_limit,
        include_user_memories=True,
        include_knowledge_memories=True,
    )


def persist_indexes() -> None:
    """将 FAISS 索引与元数据落盘。"""
    vector_memory_service.save()


def stats() -> dict[str, Any]:
    """向量库条目统计。"""
    return vector_memory_service.get_stats()
