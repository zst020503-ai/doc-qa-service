import hashlib
import logging
import math
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

SYSTEM_PROMPT = (
    "你是企业文档助手。只能依据给定的资料回答问题。"
    "如果资料中没有答案，直接回答「资料中没有找到相关内容」，不要猜测。"
    "回答时在句末用 [编号] 标注引用来源。语言简洁，不要复述资料原文。"
)


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    tokens = _WORD_RE.findall(lowered)
    cjk = _CJK_RE.findall(lowered)
    tokens.extend("".join(cjk[i : i + 2]) for i in range(len(cjk) - 1))
    tokens.extend(cjk)
    return tokens or ["_"]


def hash_embedding(text: str, dim: int) -> list[float]:
    """词法哈希向量，仅用于没有 API Key 时跑通链路，不代表语义效果。"""
    vector = [0.0] * dim
    for token in _tokens(text):
        digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        index = digest % dim
        sign = 1.0 if (digest >> 8) & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _openai_embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    batch_size = 32
    with httpx.Client(timeout=60.0) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embedding_model, "input": batch},
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors.extend(item["embedding"] for item in data)
    return vectors


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        try:
            return _openai_embed(texts)
        except Exception:
            logger.exception("embedding provider failed, fallback to hash embedding")
    return [hash_embedding(text, settings.embedding_dim) for text in texts]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]


def _openai_chat(question: str, contexts: list[str]) -> str:
    context_block = "\n\n".join(
        f"[{index}] {text}" for index, text in enumerate(contexts, start=1)
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"资料：\n{context_block}\n\n问题：{question}"},
    ]
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": settings.chat_model, "messages": messages, "temperature": 0.1},
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


def _mock_chat(contexts: list[str]) -> str:
    head = contexts[0][:400].replace("\n", " ")
    return (
        "（离线示例模式：未接入大模型，以下为最相关原文片段，配置 LLM_PROVIDER=openai 后生成正式回答）\n\n"
        f"[1] {head}"
    )


def answer_question(question: str, contexts: list[str]) -> str:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        try:
            return _openai_chat(question, contexts)
        except Exception:
            logger.exception("chat provider failed, fallback to extractive answer")
    return _mock_chat(contexts)
