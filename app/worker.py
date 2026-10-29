import logging
import time

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models import Document
from app.repositories import documents
from app.services import ingest_service

logger = logging.getLogger("worker")

POLL_INTERVAL_SECONDS = 2.0
IDLE_LOG_EVERY = 60


def run_once() -> bool:
    with SessionLocal() as db:
        claimed = documents.claim_pending(db)
    if claimed is None:
        return False

    with SessionLocal() as db:
        document = db.get(Document, claimed.id)
        if document is None:
            return True
        ingest_service.process_document(db, document)
    return True


def main() -> None:
    setup_logging()
    logger.info("worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    idle_cycles = 0
    while True:
        try:
            worked = run_once()
        except Exception:
            logger.exception("task failed")
            time.sleep(3)
            continue

        if worked:
            idle_cycles = 0
            continue

        idle_cycles += 1
        if idle_cycles % IDLE_LOG_EVERY == 0:
            logger.info("worker idle, %s cycles without task", idle_cycles)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
