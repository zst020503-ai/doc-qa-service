from sqlalchemy import delete as sql_delete
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import STATUS_READY, Chunk, Document


def bulk_create(db: Session, rows: list[dict]) -> None:
    if not rows:
        return
    db.execute(insert(Chunk), rows)
    db.commit()


def delete_by_document(db: Session, document_id: int) -> None:
    db.execute(sql_delete(Chunk).where(Chunk.document_id == document_id))
    db.commit()


def search(
    db: Session, owner_id: int, query_vector: list[float], top_k: int
) -> list[tuple]:
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.filename,
            Chunk.seq,
            Chunk.content,
            distance,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.owner_id == owner_id, Document.status == STATUS_READY)
        .order_by(distance)
        .limit(top_k)
    )
    return list(db.execute(statement).all())
