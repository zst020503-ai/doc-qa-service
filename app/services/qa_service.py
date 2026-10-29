import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User
from app.providers.llm import answer_question, embed_one
from app.repositories import chunks
from app.schemas import AskResponse, Citation

REFUSAL_TEXT = "文档中没有找到相关内容。"


def _to_citation(row) -> Citation:
    return Citation(
        document_id=row.document_id,
        filename=row.filename,
        seq=row.seq,
        snippet=row.content[:200].replace("\n", " "),
        score=round(1 - float(row.distance), 4),
    )


def ask(db: Session, user: User, question: str, top_k: int | None = None) -> AskResponse:
    started = time.perf_counter()
    limit = top_k or settings.retrieve_top_k

    vector = embed_one(question)
    rows = chunks.search(db, user.id, vector, limit)

    if not rows:
        return AskResponse(
            answer=REFUSAL_TEXT,
            refused=True,
            citations=[],
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    best_score = 1 - float(rows[0].distance)
    if best_score < settings.answer_threshold:
        return AskResponse(
            answer=REFUSAL_TEXT + "以下是相似度最高的片段，供你自行判断。",
            refused=True,
            citations=[_to_citation(row) for row in rows[:3]],
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    contexts = [
        f"{row.filename} 第 {row.seq + 1} 段：{row.content}" for row in rows
    ]
    answer = answer_question(question, contexts)

    return AskResponse(
        answer=answer,
        refused=False,
        citations=[_to_citation(row) for row in rows],
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
