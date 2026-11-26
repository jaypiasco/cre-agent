"""PDF text extraction and Vision PNG fallback using PyMuPDF."""

import base64
from dataclasses import dataclass, field
from typing import List, Literal

import pymupdf as fitz


@dataclass
class ParsedPDF:
    """Result of inspecting and parsing an uploaded PDF."""

    mode: Literal["text", "vision"]
    text: str = ""
    images_b64: List[str] = field(default_factory=list)
    page_count: int = 0


def parse_pdf(
    pdf_bytes: bytes,
    min_chars_per_page: int = 50,
    max_vision_pages: int = 5,
    dpi: int = 150,
) -> ParsedPDF:
    """Extract text from a PDF, falling back to base64 PNG rendering for scanned PDFs."""
    if not pdf_bytes:
        raise ValueError("Uploaded PDF file is empty.")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Invalid or corrupted PDF file: {exc}") from exc

    try:
        page_count = len(doc)
        if page_count == 0:
            raise ValueError("PDF contains zero pages.")

        page_texts: List[str] = []
        for page_idx in range(page_count):
            page = doc[page_idx]
            page_texts.append(page.get_text("text").strip())

        combined_text = "\n\n".join(t for t in page_texts if t)
        total_chars = sum(len(t) for t in page_texts)

        if total_chars >= min_chars_per_page * page_count:
            return ParsedPDF(
                mode="text",
                text=combined_text,
                images_b64=[],
                page_count=page_count,
            )

        # Scanned or image-only PDF: render up to max_vision_pages as PNGs
        images_b64: List[str] = []
        for page_idx in range(min(page_count, max_vision_pages)):
            page = doc[page_idx]
            pixmap = page.get_pixmap(dpi=dpi)
            png_bytes = pixmap.tobytes("png")
            images_b64.append(base64.b64encode(png_bytes).decode("ascii"))

        return ParsedPDF(
            mode="vision",
            text=combined_text,
            images_b64=images_b64,
            page_count=page_count,
        )
    finally:
        doc.close()
