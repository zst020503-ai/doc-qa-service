import os
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.models import Document, User
from app.repositories import chunks, documents

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown"}


def create_document(db: Session, user: User, filename: str, content: bytes) -> Document:
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"文件超过 {settings.max_upload_mb}MB", 413)
    if not content:
        raise AppError("EMPTY_FILE", "文件内容为空", 422)

    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError("UNSUPPORTED_FILE_TYPE", "只支持 pdf / md / txt", 415)

    os.makedirs(settings.upload_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(settings.upload_dir, stored_name)
    with open(file_path, "wb") as handle:
        handle.write(content)

    return documents.create(db, user.id, filename, file_path)


def list_documents(
    db: Session, user: User, limit: int, offset: int
) -> tuple[list[Document], int]:
    return documents.list_by_owner(db, user.id, limit, offset)


def get_document(db: Session, user: User, document_id: int) -> Document:
    document = documents.get(db, document_id)
    if document is None or document.owner_id != user.id:
        raise NotFound("文档不存在")
    return document


def delete_document(db: Session, user: User, document_id: int) -> None:
    document = get_document(db, user, document_id)
    file_path = document.file_path
    chunks.delete_by_document(db, document_id)
    documents.delete(db, document)
    if os.path.exists(file_path):
        os.remove(file_path)
