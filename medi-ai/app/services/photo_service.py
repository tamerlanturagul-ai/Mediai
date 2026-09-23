"""Photo envelope service (TASK-008, decision B4-variant-1).

A photo is an ENVELOPE for the doctor and NEVER a diagnostic signal:
- ``evaluate_final`` (services/triage_service.py) never reads ``photo_ids``
  and the score / conditions / diet builders never see image bytes.
- This module only stores the file and computes a capture-quality hint
  (ok | too_dark | too_blurry) with Pillow heuristics. NO ML, NO diagnosis.

Quality heuristics (Pillow only, thresholds documented below):
- brightness: mean of the grayscale histogram, range 0..255.
  ``mean < MEAN_BRIGHTNESS_DARK_BELOW`` -> "too_dark".
- sharpness: variance of the difference image ``gray - GaussianBlur(gray)``
  (computed from histograms, no numpy). Sharp captures change a lot under
  blur (high variance), blurry/uniform captures barely change (low variance).
  ``variance < BLUR_VARIANCE_SHARP_ABOVE`` -> "too_blurry".
  A uniform frame (e.g. solid gray) therefore reports "too_blurry".

Calibration (200x200 synthetic probes, Pillow 12):
  checkerboard  -> brightness 142.5, blur-var 1145.9  (ok)
  uniform dark  -> brightness 10.0,  blur-var 0.0     (too_dark)
  uniform gray  -> brightness 128.0, blur-var 0.0     (too_blurry)
  checker+blur5 -> brightness 142.5, blur-var 3.7     (too_blurry)
  noise texture -> brightness 132.8, blur-var 115.6   (ok)
Chosen cutoffs sit in the gaps: brightness 40.0, blur variance 50.0.
Darkness is checked first: a dark AND blurry frame reports "too_dark".
"""
from __future__ import annotations

import io
import uuid
import warnings
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

from PIL import Image, ImageChops, ImageFilter
from PIL.Image import DecompressionBombError, DecompressionBombWarning

# TASK-009 P0: hard pixel cap against decompression bombs (default Pillow
# limit is ~178 MP). Anything above is rejected in save_photo (422);
# warnings are escalated to errors so the 40 MP bound is strict.
Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_PIXELS = Image.MAX_IMAGE_PIXELS

PhotoQuality = Literal["ok", "too_dark", "too_blurry", "unknown"]

# --- storage ---
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_PHOTOS_PER_TRIAGE = 3
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# --- quality thresholds (see calibration table in module docstring) ---
MEAN_BRIGHTNESS_DARK_BELOW = 40.0
BLUR_VARIANCE_SHARP_ABOVE = 50.0

HINTS: Dict[str, str] = {
    "ok": "Качество достаточное для врача.",
    "too_dark": "Фото слишком тёмное — переснимите при хорошем освещении.",
    "too_blurry": "Фото размыто — держите камеру неподвижно и переснимите.",
    # TASK-009: stored file became unreadable after upload (never silent "ok").
    "unknown": "Не удалось оценить качество фото.",
}

# In-memory cache photo_id -> quality (source of truth for quality;
# files on disk are the source of truth for existence).
_META: Dict[str, Dict[str, str]] = {}


def _hist_mean_var(hist: list[int]) -> Tuple[float, float]:
    total = sum(hist)
    if not total:
        return 0.0, 0.0
    mean = sum(i * c for i, c in enumerate(hist)) / total
    ex2 = sum(i * i * c for i, c in enumerate(hist)) / total
    return mean, max(0.0, ex2 - mean * mean)


def assess_quality(img: Image.Image) -> Tuple[PhotoQuality, float, float]:
    """Heuristic capture quality. Returns (quality, brightness, blur_var)."""
    gray = img.convert("L")
    brightness, _ = _hist_mean_var(gray.histogram())
    if brightness < MEAN_BRIGHTNESS_DARK_BELOW:
        return "too_dark", brightness, 0.0
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
    diff = ImageChops.difference(gray, blurred)
    _, blur_var = _hist_mean_var(diff.histogram())
    if blur_var < BLUR_VARIANCE_SHARP_ABOVE:
        return "too_blurry", brightness, blur_var
    return "ok", brightness, blur_var


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def photo_exists(photo_id: str) -> bool:
    """True iff photo_id is a UUID and its file is present in UPLOAD_DIR."""
    if not _valid_uuid(photo_id):
        return False
    if not UPLOAD_DIR.is_dir():
        return False
    for ext in ALLOWED_EXTENSIONS:
        if (UPLOAD_DIR / f"{photo_id}{ext}").is_file():
            return True
    return False


def get_photo_info(photo_id: str) -> Optional[Dict[str, str]]:
    """Return {photo_id, quality} for a stored photo, or None if unknown."""
    if not photo_exists(photo_id):
        return None
    cached = _META.get(photo_id)
    if cached is not None:
        return {"photo_id": photo_id, "quality": cached["quality"]}
    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{photo_id}{ext}"
        if path.is_file():
            try:
                with Image.open(path) as img:
                    img.load()
                    quality, _, _ = assess_quality(img)
            except Exception:
                # TASK-009 P0: a corrupt/unreadable stored file must NEVER
                # report a silent "ok" — quality is honestly "unknown".
                quality = "unknown"
            _META[photo_id] = {"quality": quality}
            return {"photo_id": photo_id, "quality": quality}
    return None


class PhotoUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def save_photo(data: bytes, content_type: str | None, filename: str | None) -> Dict[str, str]:
    """Validate, store and assess an uploaded image.

    Raises PhotoUploadError with status_code 413 (oversize), 400 (wrong
    type) or 422 (unreadable image / pixel-bomb over MAX_IMAGE_PIXELS).
    Returns {photo_id, quality, hint}.
    """
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoUploadError(
            f"Файл слишком большой ({len(data)} байт, максимум {MAX_PHOTO_BYTES}).",
            status_code=413,
        )
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = Path(filename or "").suffix.lower()
    if ctype not in ALLOWED_CONTENT_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise PhotoUploadError(
            "Недопустимый тип файла: разрешены jpeg/png/webp.",
            status_code=400,
        )
    # TASK-009 P0: escalate DecompressionBombWarning to an error so the
    # 40 MP cap is enforced strictly (Pillow only warns between 1x and 2x).
    with warnings.catch_warnings():
        warnings.simplefilter("error", DecompressionBombWarning)
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
            fmt = img.format
        except (DecompressionBombError, DecompressionBombWarning) as exc:
            raise PhotoUploadError(
                "Изображение отклонено: превышен лимит размера.",
                status_code=422,
            ) from exc
        except Exception as exc:
            raise PhotoUploadError("Файл не является изображением.", status_code=422) from exc
    if fmt not in _FORMAT_TO_EXT:
        raise PhotoUploadError(
            "Недопустимый тип файла: разрешены jpeg/png/webp.",
            status_code=400,
        )
    # Backstop: explicit pixel count (some decoders may not warn).
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise PhotoUploadError(
            "Изображение отклонено: превышен лимит размера.",
            status_code=422,
        )
    quality, _, _ = assess_quality(img)
    photo_id = str(uuid.uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{photo_id}{_FORMAT_TO_EXT[fmt]}").write_bytes(data)
    _META[photo_id] = {"quality": quality}
    return {"photo_id": photo_id, "quality": quality, "hint": HINTS[quality]}
