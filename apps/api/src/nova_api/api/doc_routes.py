from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.deps import require
from ..config import get_settings
from ..db import get_db
from ..models import Document, DocumentChunk, User
from ..rag import service
from ..rag.extract import ExtractionError

router = APIRouter(prefix="/api/v1/documents", tags=["knowledge"])


class DocumentOut(BaseModel):
    id: str
    filename: str
    version: int
    ingestion_status: str
    error: str | None = None
    access_policy: str
    created_at: datetime
    chunk_count: int = 0


def _out(db: Session, d: Document) -> DocumentOut:
    n = db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == d.id))
    return DocumentOut(id=d.id, filename=d.filename, version=d.version,
                       ingestion_status=d.ingestion_status, error=d.error,
                       access_policy=d.access_policy, created_at=d.created_at, chunk_count=n or 0)


def _readable(db: Session, doc_id: str, user: User) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or not service.can_read(user, doc):
        raise HTTPException(404, "Document not found")
    return doc


def _manageable(db: Session, doc_id: str, user: User) -> Document:
    doc = _readable(db, doc_id, user)
    if not service.can_manage(user, doc):
        raise HTTPException(403, "Forbidden")
    return doc


@router.post("", response_model=DocumentOut, status_code=201)
async def upload(file: UploadFile = File(...), shared: bool = Form(False),
                 user: User = Depends(require("docs:own")), db: Session = Depends(get_db)):
    if shared and user.role != "admin":
        raise HTTPException(403, "Only admins can share documents")
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # bounded read: never buffer an unbounded upload
    try:
        doc = service.ingest(db, user, file.filename or "", data, shared=shared)
    except ExtractionError as e:
        audit(db, user.id, "document.upload", "document", None, "denied")
        raise HTTPException(422, str(e)) from e
    audit(db, user.id, "document.upload", "document", doc.id, doc.ingestion_status)
    return _out(db, doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(user: User = Depends(require("docs:own")), db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).where(
        (Document.owner_id == user.id) | (Document.access_policy == "shared"))
        .order_by(Document.created_at.desc())).all()
    return [_out(db, d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, user: User = Depends(require("docs:own")),
                 db: Session = Depends(get_db)):
    return _out(db, _readable(db, document_id, user))


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, user: User = Depends(require("docs:own")),
                    db: Session = Depends(get_db)):
    doc = _manageable(db, document_id, user)
    service.delete_document(db, doc)
    audit(db, user.id, "document.delete", "document", document_id, "ok")


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex(document_id: str, user: User = Depends(require("docs:own")),
            db: Session = Depends(get_db)):
    doc = service.reindex(db, _manageable(db, document_id, user))
    audit(db, user.id, "document.reindex", "document", doc.id, doc.ingestion_status)
    return _out(db, doc)
