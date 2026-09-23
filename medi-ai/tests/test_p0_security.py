"""P0 security tests (TASK-009).

Covers: generic 500/422 bodies (no leaks), request size limits
(symptoms_text 4000 / tags 20x64 -> 422, 10 MB text -> 422, oversize
upload -> 413), corrupt stored image -> quality "unknown", pixel-bomb
rejection (MAX_IMAGE_PIXELS), API-key auth (401, /api/health open),
rate limiting (429).

Isolation: an autouse fixture clears API_KEYS (open-by-default for dev)
and resets the slowapi in-memory storage before AND after every test, so
this module is quota-neutral to the rest of the suite (same process,
same "testclient" IP).
"""
from __future__ import annotations

import io
import logging
import uuid

import pytest
from app.main import (
    GENERIC_AUTH_ERROR,
    GENERIC_RATE_LIMIT_ERROR,
    GENERIC_SERVER_ERROR,
    GENERIC_VALIDATION_ERROR,
    app,
)
from app.schemas import PhotoAttachment
from app.security import limiter
from app.services import photo_service
from app.services.photo_service import (
    MAX_IMAGE_PIXELS,
    MAX_PHOTO_BYTES,
    UPLOAD_DIR,
    PhotoUploadError,
    get_photo_info,
)
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

client = TestClient(app)

TEST_KEY = "p0-test-key-123"


@pytest.fixture(autouse=True)
def _isolate_security(monkeypatch):
    """No ambient API_KEYS; fresh rate-limit window around every test."""
    monkeypatch.delenv("API_KEYS", raising=False)
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def clean_uploads():
    before_files = set(UPLOAD_DIR.glob("*")) if UPLOAD_DIR.is_dir() else set()
    before_meta = set(photo_service._META)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if UPLOAD_DIR.is_dir():
        for p in UPLOAD_DIR.glob("*"):
            if p not in before_files and p.is_file():
                p.unlink()
    for pid in set(photo_service._META) - before_meta:
        photo_service._META.pop(pid, None)


def _auth(key: str = TEST_KEY):
    return {"X-API-Key": key}


def _enable_auth(monkeypatch):
    monkeypatch.setenv("API_KEYS", TEST_KEY)


def _initial_payload(**extra):
    base = {
        "age": 35, "sex": "male", "height_cm": 175.0, "weight_kg": 78.0,
        "body_zone": "живот", "symptoms_text": "боль внизу живота справа, тошнота",
        "tags": ["острая боль"], "request_diet": False, "lang": "ru",
    }
    base.update(extra)
    return base


def _final_payload(**extra):
    base = _initial_payload()
    base["answers"] = [
        {"question_id": "q1", "answer": "no"},
        {"question_id": "q2", "answer": "no"},
        {"question_id": "q3", "answer": "no"},
    ]
    base.update(extra)
    return base


def _checker_png(size=200, cell=10) -> bytes:
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- 1. generic error bodies -------------------------------------------------

LEAK_MARKERS = ("Traceback", ".py", "app/", "SECRET-LEAK-MARKER", "File \"")


def test_422_body_is_generic():
    r = client.post("/api/triage/final", json={"bad": 1})
    assert r.status_code == 422
    assert r.json() == {"detail": GENERIC_VALIDATION_ERROR}
    r = client.post("/api/triage/initial", json=_initial_payload(symptoms_text="x"))
    assert r.status_code == 422
    assert r.json() == {"detail": GENERIC_VALIDATION_ERROR}
    for resp in (r,):
        for marker in LEAK_MARKERS:
            assert marker not in resp.text


def test_500_body_is_generic_and_logged(monkeypatch, caplog):
    def boom(req):
        raise RuntimeError("SECRET-LEAK-MARKER explodes in app/triage_engine.py:999")

    monkeypatch.setattr("app.main.evaluate_final", boom)
    with caplog.at_level(logging.ERROR):
        r = client.post("/api/triage/final", json=_final_payload())
    assert r.status_code == 500, r.text
    assert r.json() == {"detail": GENERIC_SERVER_ERROR}
    for marker in LEAK_MARKERS:
        assert marker not in r.text
    # ...but the server log keeps the full traceback for operators.
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "triage evaluation failed" in logged
    assert any(rec.exc_info is not None for rec in caplog.records)


def test_sport_500_body_is_generic(monkeypatch):
    def boom(req):
        raise RuntimeError("SECRET-LEAK-MARKER explodes in app/sport_engine.py:999")

    monkeypatch.setattr("app.main.build_sport_plan", boom)
    r = client.post("/api/sport/plan", json={
        "age": 30, "sex": "male", "height_cm": 170, "weight_kg": 70,
        "goal": "lose", "activity_level": "light",
        "contraindications": [], "lang": "ru",
    })
    assert r.status_code == 500, r.text
    assert r.json() == {"detail": GENERIC_SERVER_ERROR}
    assert "SECRET-LEAK-MARKER" not in r.text


# --- 2. request size limits --------------------------------------------------

def test_10mb_symptoms_text_rejected():
    r = client.post("/api/triage/initial", json=_initial_payload(symptoms_text="x" * (10 * 1024 * 1024)))
    assert r.status_code == 422, r.status_code
    assert r.json() == {"detail": GENERIC_VALIDATION_ERROR}


def test_symptoms_text_boundary():
    ok = client.post("/api/triage/initial", json=_initial_payload(symptoms_text="x" * 4000))
    assert ok.status_code == 200, ok.text
    over = client.post("/api/triage/final", json=_final_payload(symptoms_text="x" * 4001))
    assert over.status_code == 422
    assert over.json() == {"detail": GENERIC_VALIDATION_ERROR}


def test_tags_limits():
    many = client.post("/api/triage/initial", json=_initial_payload(tags=[f"t{i}" for i in range(21)]))
    assert many.status_code == 422
    long_tag = client.post("/api/triage/initial", json=_initial_payload(tags=["x" * 65]))
    assert long_tag.status_code == 422
    edge = client.post("/api/triage/initial", json=_initial_payload(tags=["x" * 64 for _ in range(20)]))
    assert edge.status_code == 200, edge.text


# --- 3. upload caps: 413 -----------------------------------------------------

def test_oversize_upload_rejected_413():
    big = b"a" * (MAX_PHOTO_BYTES + 1024 * 1024)  # 9 MB of junk
    r = client.post("/api/triage/photo", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413, r.status_code
    assert "Traceback" not in r.text


def test_just_over_cap_upload_rejected_413():
    # 8 MB + 1 byte: slips past the Content-Length pre-check slack and must
    # be caught by the exact chunked-read cap on file bytes.
    data = b"b" * (MAX_PHOTO_BYTES + 1)
    r = client.post("/api/triage/photo", files={"file": ("edge.png", data, "image/png")})
    assert r.status_code == 413, r.status_code


# --- 4. corrupt image -> "unknown" (never silent "ok") -----------------------

def test_corrupt_stored_png_reports_unknown(clean_uploads):
    pid = str(uuid.uuid4())
    (UPLOAD_DIR / f"{pid}.png").write_bytes(b"\x89PNG\r\nnot really png")
    try:
        info = get_photo_info(pid)
        assert info is not None
        assert info["quality"] == "unknown"
        r = client.post("/api/triage/final", json=_final_payload(photo_ids=[pid]))
        assert r.status_code == 200, r.text
        assert r.json()["photos_attached"] == [{"photo_id": pid, "quality": "unknown"}]
        PhotoAttachment(photo_id=pid, quality="unknown")  # schema accepts it
    finally:
        (UPLOAD_DIR / f"{pid}.png").unlink(missing_ok=True)
        photo_service._META.pop(pid, None)


# --- 5. pixel bomb -----------------------------------------------------------

def test_max_image_pixels_is_40mp():
    assert MAX_IMAGE_PIXELS == 40_000_000
    import PIL.Image

    assert PIL.Image.MAX_IMAGE_PIXELS == 40_000_000


def _uniform_png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("P", (width, height)).save(buf, format="PNG")  # uniform -> KBs on disk
    return buf.getvalue()


@pytest.mark.parametrize("w,h", [(7000, 7000), (12000, 8000)])
def test_pixel_bomb_rejected(clean_uploads, w, h):
    assert w * h > MAX_IMAGE_PIXELS
    data = _uniform_png(w, h)
    assert len(data) < MAX_PHOTO_BYTES  # tiny bytes, huge pixels: the bomb shape
    with pytest.raises(PhotoUploadError) as ei:
        photo_service.save_photo(data, "image/png", "bomb.png")
    assert ei.value.status_code == 422
    r = client.post("/api/triage/photo", files={"file": ("bomb.png", data, "image/png")})
    assert r.status_code == 422, r.status_code


# --- 6. auth -----------------------------------------------------------------

def test_no_key_401_when_enforced(monkeypatch):
    _enable_auth(monkeypatch)
    assert client.get("/api/conditions").status_code == 401
    r = client.post("/api/triage/initial", json=_initial_payload())
    assert r.status_code == 401
    assert r.json() == {"detail": GENERIC_AUTH_ERROR}
    r = client.post("/api/triage/final", json=_final_payload())
    assert r.status_code == 401
    r = client.post("/api/triage/photo",
                    files={"file": ("x.png", _checker_png(), "image/png")})
    assert r.status_code == 401
    # wrong key is also 401
    r = client.post("/api/triage/initial", json=_initial_payload(), headers=_auth("wrong"))
    assert r.status_code == 401


def test_health_stays_open_and_key_allows_access(monkeypatch):
    _enable_auth(monkeypatch)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok", "service": "medi-ai"}
    r = client.post("/api/triage/initial", json=_initial_payload(), headers=_auth())
    assert r.status_code == 200, r.text
    # unenforced (no env): open without a key
    monkeypatch.delenv("API_KEYS")
    r = client.post("/api/triage/initial", json=_initial_payload())
    assert r.status_code == 200, r.text


# --- 7. rate limiting --------------------------------------------------------

def test_flood_triaged_initial_429(monkeypatch):
    _enable_auth(monkeypatch)  # flood with a valid key: 429, not 401
    statuses = []
    for _ in range(40):  # budget is 30/min; 40 guarantees overflow
        r = client.post("/api/triage/initial", json=_initial_payload(), headers=_auth())
        statuses.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in statuses, statuses
    assert r.json() == {"detail": GENERIC_RATE_LIMIT_ERROR}
    assert r.status_code == 429


def test_flood_upload_429(monkeypatch, clean_uploads):
    _enable_auth(monkeypatch)
    statuses = []
    for _ in range(15):  # budget is 10/min
        r = client.post(
            "/api/triage/photo",
            files={"file": ("x.png", _checker_png(), "image/png")},
            headers=_auth(),
        )
        statuses.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in statuses, statuses
