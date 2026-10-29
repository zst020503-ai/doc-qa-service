import logging
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import STATUS_FAILED, STATUS_READY, Document
from app.providers.llm import embed_texts
from app.repositories import chunks, documents

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def split_text(text: str, size: int, overlap: int) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    pieces: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + size
        piece = cleaned[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(cleaned):
            break
        start = end - overlap
    return pieces


def process_document(db: Session, document: Document) -> int:
    """解析 -> 切分 -> 向量化 -> 落库。失败时把原因写回文档状态。"""
    try:
        text = extract_text(document.file_path)
        pieces = split_text(text, settings.chunk_size, settings.chunk_overlap)
        if not pieces:
            raise ValueError("没有提取到可用的文本内容")

        vectors = embed_texts(pieces)
        rows = [
            {
                "document_id": document.id,
                "seq": index,
                "content": piece,
                "embedding": vector,
            }
            for index, (piece, vector) in enumerate(zip(pieces, vectors))
        ]
        chunks.delete_by_document(db, document.id)
        chunks.bulk_create(db, rows)
        documents.update_status(db, document, STATUS_READY, chunk_count=len(rows))
        logger.info("document %s indexed with %s chunks", document.id, len(rows))
        return len(rows)
    except Exception as exc:
        logger.exception("document %s failed", document.id)
        documents.update_status(db, document, STATUS_FAILED, error=str(exc)[:500])
        raise
