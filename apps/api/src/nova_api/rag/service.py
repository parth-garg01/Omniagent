import hashlib
import json
import os

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Document, DocumentChunk, User
from ..orchestration.types import Source
from .chunking import chunk_text
from .embeddings import cosine, get_embedder
from .extract import ALLOWED, ExtractionError, extract_segments, validate_signature

TOP_K = 5


def safe_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    return "".join(c for c in base if c.isprintable() and c not in '<>"')[:200] or "unnamed"


def validate_upload(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED:
        raise ExtractionError(f"Unsupported file type; allowed: {', '.join(sorted(ALLOWED))}")
    if not data:
        raise ExtractionError("File is empty")
    if len(data) > get_settings().max_upload_bytes:
        raise ExtractionError("File exceeds the upload size limit")
    validate_signature(ext, data)
    return ext


def _index(db: Session, doc: Document, segments: list[tuple[str, dict]]) -> None:
    s = get_settings()
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    pieces: list[tuple[str, dict]] = []
    for text, meta in segments:
        pieces += [(c, meta) for c in chunk_text(text, s.chunk_size, s.chunk_overlap)]
    vectors = get_embedder().embed([p for p, _ in pieces])
    for i, ((content, meta), vec) in enumerate(zip(pieces, vectors, strict=True)):
        db.add(DocumentChunk(document_id=doc.id, chunk_index=i, content=content,
                             embedding=vec, meta=meta))


def ingest(db: Session, owner: User, filename: str, data: bytes, shared: bool = False) -> Document:
    filename = safe_filename(filename)
    ext = validate_upload(filename, data)
    doc = Document(owner_id=owner.id, filename=filename,
                   content_hash=hashlib.sha256(data).hexdigest(),
                   access_policy="shared" if shared else "private", ingestion_status="processing")
    db.add(doc)
    db.commit()
    try:
        segments = extract_segments(ext, data)
        doc.raw_text = json.dumps(segments)
        _index(db, doc, segments)
        doc.ingestion_status = "ready"
    except ExtractionError as e:
        db.rollback()
        doc = db.get(Document, doc.id)
        doc.ingestion_status, doc.error = "failed", str(e)
    db.commit()
    return doc


def reindex(db: Session, doc: Document) -> Document:
    segments = [tuple(x) for x in json.loads(doc.raw_text or "[]")]
    if not segments:
        doc.ingestion_status, doc.error = "failed", "No stored text to index"
    else:
        doc.ingestion_status = "processing"
        db.commit()
        _index(db, doc, segments)
        doc.version += 1
        doc.ingestion_status, doc.error = "ready", None
    db.commit()
    return doc


def delete_document(db: Session, doc: Document) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    db.delete(doc)
    db.commit()


def can_read(user: User, doc: Document) -> bool:
    return doc.owner_id == user.id or doc.access_policy == "shared"


def can_manage(user: User, doc: Document) -> bool:
    return doc.owner_id == user.id or (user.role == "admin" and doc.access_policy == "shared")


def retrieve(db: Session, user: User, query: str, top_k: int = TOP_K) -> list[Source]:
    """Permission filter is applied in the query itself, before any scoring."""
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.ingestion_status == "ready",
               (Document.owner_id == user.id) | (Document.access_policy == "shared"))
    ).all()
    qv = get_embedder().embed([query])[0]
    min_score = get_settings().retrieval_min_score
    # Chunks indexed by an older dense embedder (list) are skipped until reindexed.
    scored = sorted(((cosine(qv, c.embedding), c, d) for c, d in rows
                     if isinstance(c.embedding, dict)), key=lambda t: -t[0])
    return [Source(document_id=d.id, filename=d.filename, chunk_index=c.chunk_index,
                   content=c.content, score=round(sc, 4), meta=c.meta or {})
            for sc, c, d in scored[:top_k] if sc >= min_score]
