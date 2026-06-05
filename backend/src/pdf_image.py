"""Utilities for scanned (image-only) PDFs: detection and page stitching."""

from __future__ import annotations

import base64
import io
import logging
import urllib.request
from typing import Tuple

import fitz
from PIL import Image
from langchain_community.document_loaders import PyMuPDFLoader

logger = logging.getLogger(__name__)

MIN_PAGE_TEXT_CHARS = 100
DEFAULT_RENDER_DPI = 150


def is_scanned_pdf(pdf_source: str) -> bool:
    """
    True when the PDF has no meaningful extractable text (image capture / scan).
    Uses the same heuristic as manual inspection: no page exceeds MIN_PAGE_TEXT_CHARS.
    """
    loader = PyMuPDFLoader(pdf_source)
    docs = loader.load()
    if not docs:
        return True
    text_pages = sum(
        1 for doc in docs if len(doc.page_content.strip()) > MIN_PAGE_TEXT_CHARS
    )
    return text_pages == 0


def _fetch_pdf_bytes(pdf_source: str) -> bytes:
    if pdf_source.startswith(("http://", "https://")):
        with urllib.request.urlopen(pdf_source, timeout=120) as response:
            return response.read()
    with open(pdf_source, "rb") as file:
        return file.read()


def pdf_to_vertical_image(pdf_path: str, output_path: str, dpi: int = DEFAULT_RENDER_DPI) -> str:
    """Render all PDF pages into one vertical image file."""
    image_bytes, _ = pdf_to_vertical_image_bytes(pdf_path, dpi=dpi)
    with open(output_path, "wb") as file:
        file.write(image_bytes)
    return output_path


def pdf_to_vertical_image_bytes(
    pdf_source: str,
    dpi: int = DEFAULT_RENDER_DPI,
    mime_type: str = "image/jpeg",
) -> Tuple[bytes, str]:
    """Render all PDF pages into one vertical JPEG and return (bytes, mime_type)."""
    pdf_bytes = _fetch_pdf_bytes(pdf_source)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_images = []

    for page in doc:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        page_images.append(
            Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        )

    doc.close()

    if not page_images:
        raise ValueError(f"No pages found in PDF: {pdf_source}")

    width = max(img.width for img in page_images)
    height = sum(img.height for img in page_images)
    combined = Image.new("RGB", (width, height), "white")

    y_offset = 0
    for img in page_images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    buffer = io.BytesIO()
    combined.save(buffer, format="JPEG", quality=85)
    logger.info(
        "Rendered scanned PDF to vertical image (%sx%s, %s pages)",
        width,
        height,
        len(page_images),
    )
    return buffer.getvalue(), mime_type


def pdf_to_vertical_image_base64(pdf_source: str, dpi: int = DEFAULT_RENDER_DPI) -> Tuple[str, str]:
    """Return (base64_string, mime_type) for multimodal LLM input."""
    image_bytes, mime_type = pdf_to_vertical_image_bytes(pdf_source, dpi=dpi)
    return base64.b64encode(image_bytes).decode("utf-8"), mime_type
