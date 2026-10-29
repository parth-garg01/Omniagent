import io
import re
import zipfile

MAX_TEXT_CHARS = 1_000_000
MAX_PDF_PAGES = 200
MAX_DOCX_UNCOMPRESSED = 20_000_000
ALLOWED = {".pdf", ".txt", ".md", ".docx"}


class ExtractionError(ValueError):
    pass


def validate_signature(ext: str, data: bytes) -> None:
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ExtractionError("File content is not a PDF")
    if ext == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise ExtractionError("File content is not a DOCX")
    if ext in (".txt", ".md") and b"\x00" in data[:4096]:
        raise ExtractionError("File content is not text")


def _norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.replace("\r\n", "\n")).strip()


def extract_segments(ext: str, data: bytes) -> list[tuple[str, dict]]:
    """Returns [(text, metadata)] where metadata may hold `page` or `section`."""
    validate_signature(ext, data)
    if ext == ".txt":
        segs = [(_norm(_decode(data)), {})]
    elif ext == ".md":
        segs = _markdown(_decode(data))
    elif ext == ".pdf":
        segs = _pdf(data)
    elif ext == ".docx":
        segs = _docx(data)
    else:
        raise ExtractionError(f"Unsupported file type: {ext}")
    segs = [(t, m) for t, m in segs if t]
    if not segs:
        raise ExtractionError("No extractable text found")
    if sum(len(t) for t, _ in segs) > MAX_TEXT_CHARS:
        raise ExtractionError("Extracted text exceeds the size limit")
    return segs


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ExtractionError("Text files must be UTF-8") from e


def _markdown(text: str) -> list[tuple[str, dict]]:
    segs: list[tuple[str, dict]] = []
    section, buf = None, []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            segs.append((_norm("\n".join(buf)), {"section": section} if section else {}))
            section, buf = m.group(1).strip(), []
        buf.append(line)
    segs.append((_norm("\n".join(buf)), {"section": section} if section else {}))
    return segs


def _pdf(data: bytes) -> list[tuple[str, dict]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"PDF exceeds {MAX_PDF_PAGES} pages")
        return [(_norm(p.extract_text() or ""), {"page": i}) for i, p in enumerate(reader.pages, 1)]
    except ExtractionError:
        raise
    except Exception as e:  # noqa: BLE001 - parser errors vary; surface a safe message
        raise ExtractionError("Could not read PDF") from e


def _docx(data: bytes) -> list[tuple[str, dict]]:
    from docx import Document

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_DOCX_UNCOMPRESSED:
                raise ExtractionError("DOCX expands beyond the allowed size")
        doc = Document(io.BytesIO(data))
        return [(_norm("\n".join(p.text for p in doc.paragraphs)), {})]
    except ExtractionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractionError("Could not read DOCX") from e
