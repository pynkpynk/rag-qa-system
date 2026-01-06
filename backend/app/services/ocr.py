import os
from typing import List, Tuple


class OCRBackend:
    def extract(
        self, path: str, *, request_id: str | None = None
    ) -> List[Tuple[int, str]]:
        raise NotImplementedError


class NoneOCRBackend(OCRBackend):
    def extract(
        self, path: str, *, request_id: str | None = None
    ) -> List[Tuple[int, str]]:
        return []


class TesseractOCRBackend(OCRBackend):
    def __init__(self) -> None:
        try:
            import pytesseract  # type: ignore
            from pdf2image import convert_from_path  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "tesseract backend unavailable (install pytesseract+pdf2image and system binaries)"
            ) from exc
        self._pytesseract = pytesseract
        self._convert = convert_from_path

    def extract(
        self, path: str, *, request_id: str | None = None
    ) -> List[Tuple[int, str]]:
        pages = []
        images = self._convert(path)
        for idx, image in enumerate(images, start=1):
            text = self._pytesseract.image_to_string(image) or ""
            text = text.strip()
            if text:
                pages.append((idx, text))
        return pages


_BACKEND_CACHE: OCRBackend | None = None
_BACKEND_NAME: str | None = None


def get_ocr_backend() -> OCRBackend:
    global _BACKEND_CACHE, _BACKEND_NAME  # noqa: PLW0603
    backend_name = (os.getenv("OCR_BACKEND", "none") or "none").strip().lower()
    if _BACKEND_CACHE is not None and _BACKEND_NAME == backend_name:
        return _BACKEND_CACHE

    if backend_name in {"", "none"}:
        backend: OCRBackend = NoneOCRBackend()
    elif backend_name == "tesseract":
        backend = TesseractOCRBackend()
    else:
        raise RuntimeError(f"OCR backend '{backend_name}' is not supported")

    _BACKEND_CACHE = backend
    _BACKEND_NAME = backend_name
    return backend
