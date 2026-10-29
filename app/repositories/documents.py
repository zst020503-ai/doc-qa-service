from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import STATUS_PENDING, STATUS_PROCESSING, Document


def create(db: Session, owner_id: int, filename: str, file_path: str) -> Document:
    document = Document(
        owner_id=owner_id,
        filename=filename,
        file_path=file_path,
        status=STATUS_PENDING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def get(db: Session, document_id: int) -> Document | None:
    return db.get(Document, document_id)


def list_by_owner(
    db: Session, owner_id: int, limit: int, offset: int
) -> tuple[list[Document], int]:
    total = db.execute(
        select(func.count()).select_from(Document).where(Document.owner_id == owner_id)
    ).scalar_one()
    documents = (
        db.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(documents), int(total)


def delete(db: Session, document: Document) -> None:
    db.delete(document)
    db.commit()


def claim_pending(db: Session) -> Document | None:
    """原子认领一条待处理任务，多 worker 并发时不会重复处理。"""
    statement = (
        select(Document)
        .where(Document.status == STATUS_PENDING)
        .order_by(Document.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    document = db.execute(statement).scalar_one_or_none()
    if document is None:
        db.rollback()
        return None
    document.status = STATUS_PROCESSING
    db.commit()
    db.refresh(document)
    return document


def update_status(
    db: Session,
    document: Document,
    status: str,
    error: str | None = None,
    chunk_count: int | None = None,
) -> None:
    document.status = status
    document.error = error
    if chunk_count is not None:
        document.chunk_count = chunk_count
    db.commit()
