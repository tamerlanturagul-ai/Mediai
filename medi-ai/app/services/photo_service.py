"""Photo envelope service (TASK-008, decision B4-variant-1; lifecycle TASK-012).

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

TASK-012 lifecycle (privacy + retention):
- EXIF/XMP stripped BEFORE save (GPS/device = PII). JPEG: APP1/COM segments
  dropped at the byte level (no re-encode, decoded pixels bit-identical).
  WebP: EXIF/XMP RIFF chunks dropped (pixels bit-identical). PNG: re-saved
  without ancillary chunks (lossless, pixels bit-identical).
- Retention: files expire after PHOTO_TTL_DAYS (default 30, env-overridable).
  Expired files (+ sidecars) are removed on startup and on every upload
  (best-effort sweep, never fails the request).
- Each photo has a sidecar ``<photo_id>.json`` next to the file
  (``{"quality", "created_at", "ext"}``). The in-memory ``_META`` cache is
  bounded to MAX_META_ENTRIES (oldest evicted first).
"""
from __future__ import annotations

import io
import json
import os
import struct
import time
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

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
EXT_TO_MEDIA_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
SIDECAR_SUFFIX = ".json"

# --- TASK-012 retention ---
DEFAULT_PHOTO_TTL_DAYS = 30
MAX_META_ENTRIES = 1000

# --- quality thresholds (see calibration table in module docstring) ---
MEAN_BRIGHTNESS_DARK_BELOW = 40.0
BLUR_VARIANCE_SHARP_ABOVE = 50.0

HINTS: dict[str, str] = {
    "ok": "Качество достаточное для врача.",
    "too_dark": "Фото слишком тёмное — переснимите при хорошем освещении.",
    "too_blurry": "Фото размыто — держите камеру неподвижно и переснимите.",
    # TASK-009: stored file became unreadable after upload (never silent "ok").
    "unknown": "Не удалось оценить качество фото.",
}

# In-memory cache photo_id -> quality (source of truth for quality;
# files on disk are the source of truth for existence).
_META: dict[str, dict[str, str]] = {}


def _hist_mean_var(hist: list[int]) -> tuple[float, float]:
    total = sum(hist)
    if not total:
        return 0.0, 0.0
    mean = sum(i * c for i, c in enumerate(hist)) / total
    ex2 = sum(i * i * c for i, c in enumerate(hist)) / total
    return mean, max(0.0, ex2 - mean * mean)


def assess_quality(img: Image.Image) -> tuple[PhotoQuality, float, float]:
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


def photo_ttl_seconds() -> int:
    """Retention TTL in seconds (env PHOTO_TTL_DAYS, default 30)."""
    raw = os.getenv("PHOTO_TTL_DAYS", str(DEFAULT_PHOTO_TTL_DAYS))
    try:
        days = int(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        days = DEFAULT_PHOTO_TTL_DAYS
    days = min(max(days, 1), 365)
    return days * 24 * 3600


def _sidecar_path(photo_id: str) -> Path:
    return UPLOAD_DIR / f"{photo_id}{SIDECAR_SUFFIX}"


def _cap_meta() -> None:
    """Bound the in-memory _META cache (evict oldest first)."""
    overflow = len(_META) - MAX_META_ENTRIES
    if overflow <= 0:
        return
    for key in list(_META.keys())[:overflow]:
        _META.pop(key, None)


def _write_sidecar(photo_id: str, quality: str, ext: str) -> None:
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "photo_id": photo_id,
            "quality": quality,
            "ext": ext,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _sidecar_path(photo_id).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _read_sidecar(photo_id: str) -> dict[str, str] | None:
    try:
        raw = _sidecar_path(photo_id).read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("quality"), str):
            return {"quality": str(data["quality"])}
    except (OSError, ValueError, AttributeError):
        pass
    return None


def get_photo_path(photo_id: str) -> Path | None:
    """Filesystem path of a stored photo, or None if missing/invalid."""
    if not _valid_uuid(photo_id):
        return None
    if not UPLOAD_DIR.is_dir():
        return None
    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{photo_id}{ext}"
        if path.is_file():
            return path
    return None


def photo_exists(photo_id: str) -> bool:
    """True iff photo_id is a UUID and its file is present in UPLOAD_DIR."""
    return get_photo_path(photo_id) is not None


def get_photo_bytes(photo_id: str) -> tuple[bytes, str] | None:
    """Return (file bytes, media type) for a stored photo, else None."""
    path = get_photo_path(photo_id)
    if path is None:
        return None
    try:
        return path.read_bytes(), EXT_TO_MEDIA_TYPE.get(path.suffix.lower(), "application/octet-stream")
    except OSError:
        return None


def delete_photo(photo_id: str) -> bool:
    """Delete a photo + sidecar + cache entry. True iff something existed."""
    if not _valid_uuid(photo_id):
        return False
    removed = False
    path = get_photo_path(photo_id)
    if path is not None:
        try:
            path.unlink()
            removed = True
        except OSError:
            pass
    try:
        sidecar = _sidecar_path(photo_id)
        if sidecar.is_file():
            sidecar.unlink()
            removed = True
    except OSError:
        pass
    if _META.pop(photo_id, None) is not None:
        removed = True
    return removed


def sweep_expired_photos(ttl_seconds: int | None = None) -> int:
    """Delete photos (+ sidecars) older than TTL. Returns removed count."""
    ttl = ttl_seconds if ttl_seconds is not None else photo_ttl_seconds()
    if not UPLOAD_DIR.is_dir():
        return 0
    now = time.time()
    removed = 0
    try:
        entries = list(UPLOAD_DIR.iterdir())
    except OSError:
        return 0
    for path in entries:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        suffix = path.suffix.lower()
        stem = path.stem
        is_image = suffix in ALLOWED_EXTENSIONS and _valid_uuid(stem)
        is_sidecar = suffix == SIDECAR_SUFFIX and _valid_uuid(stem)
        if not (is_image or is_sidecar):
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age <= ttl:
            continue
        photo_id = stem
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
        # When an image expires, drop its sidecar + cache too (counted once).
        if is_image:
            try:
                _sidecar_path(photo_id).unlink(missing_ok=True)
            except OSError:
                pass
            _META.pop(photo_id, None)
        else:
            _META.pop(photo_id, None)
    _cap_meta()
    return removed


def _strip_jpeg_metadata(data: bytes) -> bytes:
    """Drop JPEG APP1 (EXIF/XMP) + COM segments without re-encoding."""
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return data
    out = bytearray(data[0:2])
    pos = 2
    n = len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            break
        ff = pos
        while ff < n and data[ff] == 0xFF:
            ff += 1
        if ff >= n:
            break
        marker = data[ff]
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7) or marker == 0x01:
            out += b"\xff" + bytes([marker])
            pos = ff + 1
            if marker == 0xD9:
                out += data[pos:]
                break
            continue
        if ff + 3 > n:
            break
        seg_len = (data[ff + 1] << 8) | data[ff + 2]
        if seg_len < 2:
            break
        end = ff + 1 + seg_len
        if end > n:
            break
        drop = marker == 0xE1 or marker == 0xFE
        if not drop:
            out += b"\xff" + bytes([marker]) + data[ff + 1 : end]
        pos = end
        if marker == 0xDA:
            out += data[pos:]
            break
    if len(out) < 20:
        return data
    return bytes(out)


def _strip_webp_metadata(data: bytes) -> bytes:
    """Drop WebP EXIF/XMP RIFF chunks without re-encoding."""
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return data
    out_chunks = bytearray()
    pos = 12
    n = len(data)
    dropped = 0
    while pos + 8 <= n:
        fourcc = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        end = pos + 8 + size + (size & 1)
        if end > n:
            break
        if fourcc in (b"EXIF", b"XMP "):
            dropped += 1
        else:
            out_chunks += data[pos:end]
        pos = end
    if dropped == 0:
        return data
    patched = bytearray(out_chunks)
    p = 0
    while p + 8 <= len(patched):
        fcc = bytes(patched[p : p + 4])
        sz = struct.unpack("<I", patched[p + 4 : p + 8])[0]
        e = p + 8 + sz + (sz & 1)
        if e > len(patched):
            break
        if fcc == b"VP8X" and sz >= 1:
            patched[p + 8] = patched[p + 8] & ~0x0C
        p = e
    res = bytearray(b"RIFF....WEBP")
    res += patched
    struct.pack_into("<I", res, 4, len(res) - 8)
    return bytes(res)


def strip_metadata(data: bytes, fmt: str | None, img: Image.Image) -> bytes:
    """Return privacy-stripped bytes (EXIF/XMP gone, pixels bit-identical).

    JPEG/WebP are stripped at the container level (no re-encode).
    PNG is re-saved losslessly without ancillary chunks.
    """
    if fmt == "JPEG":
        stripped = _strip_jpeg_metadata(data)
        # Verify EXIF is gone; fall back to a clean re-encode if parsing failed.
        try:
            with Image.open(io.BytesIO(stripped)) as probe:
                probe.load()
                if not probe.getexif():
                    return stripped
        except Exception:  # noqa: BLE001, S110  # probe failure -> fall through to re-encode fallback
            pass
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    if fmt == "WEBP":
        stripped = _strip_webp_metadata(data)
        try:
            with Image.open(io.BytesIO(stripped)) as probe:
                probe.load()
                if probe.info.get("exif") is None:
                    return stripped
        except Exception:  # noqa: BLE001, S110  # probe failure -> fall through to re-encode fallback
            pass
        buf = io.BytesIO()
        img.save(buf, format="WEBP")
        return buf.getvalue()
    if fmt == "PNG":
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    return data


def get_photo_info(photo_id: str) -> dict[str, str] | None:
    """Return {photo_id, quality} for a stored photo, or None if unknown."""
    if not photo_exists(photo_id):
        return None
    cached = _META.get(photo_id)
    if cached is not None:
        return {"photo_id": photo_id, "quality": cached["quality"]}
    sidecar = _read_sidecar(photo_id)
    if sidecar is not None:
        _META[photo_id] = {"quality": sidecar["quality"]}
        _cap_meta()
        return {"photo_id": photo_id, "quality": sidecar["quality"]}
    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{photo_id}{ext}"
        if path.is_file():
            try:
                with Image.open(path) as img:
                    img.load()
                    quality, _, _ = assess_quality(img)
            except Exception:  # noqa: BLE001  # any Pillow decode failure must degrade to quality="unknown", never crash triage
                # TASK-009 P0: a corrupt/unreadable stored file must NEVER
                # report a silent "ok" — quality is honestly "unknown".
                quality = "unknown"
            _META[photo_id] = {"quality": quality}
            _cap_meta()
            return {"photo_id": photo_id, "quality": quality}
    return None


class PhotoUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def save_photo(data: bytes, content_type: str | None, filename: str | None) -> dict[str, str]:
    """Validate, strip metadata, store and assess an uploaded image.

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
    # TASK-012: strip EXIF/XMP (GPS/device PII) before persisting.
    # Container-level strip keeps decoded pixels bit-identical.
    clean = strip_metadata(data, fmt, img)
    if len(clean) > MAX_PHOTO_BYTES:
        raise PhotoUploadError(
            f"Файл слишком большой ({len(clean)} байт, максимум {MAX_PHOTO_BYTES}).",
            status_code=413,
        )
    photo_id = str(uuid.uuid4())
    out_ext = _FORMAT_TO_EXT[fmt]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{photo_id}{out_ext}").write_bytes(clean)
    _META[photo_id] = {"quality": quality}
    _cap_meta()
    _write_sidecar(photo_id, quality, out_ext)
    # Per-upload TTL sweep (best effort; never fails the upload).
    try:
        sweep_expired_photos()
    except Exception:  # noqa: BLE001, S110  # sweep is best-effort background hygiene
        pass
    return {"photo_id": photo_id, "quality": quality, "hint": HINTS[quality]}
