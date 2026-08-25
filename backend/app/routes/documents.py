"""Document text extraction for setup-time inputs (JD / resume uploads)."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.tenancy import OrgContext, require_role

router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 20_000


@router.post("/documents/extract")
async def extract_text(
    file: UploadFile,
    ctx: OrgContext = Depends(require_role("reviewer", "candidate")),
) -> dict[str, str]:
    """Extract plain text from an uploaded .pdf or .txt (for JD/resume fields).
    The extracted text is returned to the client; nothing is stored here —
    it lands on the session at creation, where it is auditable."""
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large (5MB max)")
    name = (file.filename or "").lower()

    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        try:
            import asyncio
            import io

            from pypdf import PdfReader

            def _extract(data: bytes) -> str:
                reader = PdfReader(io.BytesIO(data))
                return "\n".join(page.extract_text() or "" for page in reader.pages)

            # CPU-bound parsing off the event loop: a complex 5MB PDF would
            # otherwise stall every in-flight request, including live rooms
            text = await asyncio.to_thread(_extract, raw)
        except Exception as exc:  # noqa: BLE001 - surface as a clean 422
            raise HTTPException(422, f"could not read PDF: {exc}") from None
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")

    text = text.strip()
    if not text:
        raise HTTPException(422, "no extractable text found in the file")
    return {"text": text[:MAX_TEXT_CHARS], "truncated": str(len(text) > MAX_TEXT_CHARS)}
