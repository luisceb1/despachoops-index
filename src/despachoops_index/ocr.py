from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OcrResult:
    text: str
    status: str


def extract_text_with_ocr(path: Path, languages: str = "spa+eng") -> OcrResult:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return OcrResult("", "OCR_NO_DISPONIBLE")
    try:
        text = pytesseract.image_to_string(Image.open(path), lang=languages)
        return OcrResult(text or "", "OCR_OK" if text else "OCR_SIN_TEXTO")
    except Exception as exc:  # noqa: BLE001
        return OcrResult("", f"OCR_ERROR:{exc}")


def extract_pdf_text_with_ocr(path: Path, max_pages: int = 10, languages: str = "spa+eng") -> OcrResult:
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        return OcrResult("", "OCR_PDF_NO_DISPONIBLE")
    if not tesseract_available():
        return OcrResult("", "OCR_NO_DISPONIBLE")
    try:
        images = convert_from_path(str(path), dpi=200, first_page=1, last_page=max_pages)
        pages = [pytesseract.image_to_string(img, lang=languages) or "" for img in images]
    except Exception as exc:  # noqa: BLE001
        return OcrResult("", f"OCR_PDF_ERROR:{exc}")
    text = "\n".join(pages).strip()
    return OcrResult(text, f"OCR_OK;paginas={len(images)}" if text else "OCR_SIN_TEXTO")


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None
