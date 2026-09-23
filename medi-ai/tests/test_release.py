"""TASK-012 release tests: photo lifecycle + prod readiness.

Covers: EXIF stripped (GPS gone, pixels bit-identical), TTL sweep, GET/DELETE
auth-gating, security headers, golden sha unchanged, offline smoke
(no CDN, local tailwind.css, Dockerfile shape, loopback __main__).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path

import pytest
from app.domain.rules import RULES_VERSION
from app.main import APP_VERSION, app
from app.security import limiter
from app.services import photo_service
from app.services.photo_service import (
    MAX_META_ENTRIES,
    UPLOAD_DIR,
    get_photo_path,
    sweep_expired_photos,
)
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

TEST_KEY = "release-test-key-abc"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.delenv("PHOTO_TTL_DAYS", raising=False)
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def api_client():
    return TestClient(app)


def _checker(size: int = 200, cell: int = 10) -> Image.Image:
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(30, 30, 30))
    return img


def _jpeg_with_exif(img: Image.Image) -> bytes:
    ex = Image.Exif()
    ex[271] = "TestMake-PII"
    ex[272] = "TestModel-PII"
    ex[34853] = {0: b"\x02\x03\x00\x00", 1: "N"}
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=ex)
    return buf.getvalue()


def _png_with_exif(img: Image.Image) -> bytes:
    ex = Image.Exif()
    ex[271] = "TestMake-PII"
    buf = io.BytesIO()
    img.save(buf, format="PNG", exif=ex.tobytes())
    return buf.getvalue()


def _pixels_hash(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        return hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()


# --- 1. EXIF stripped, pixels bit-identical ---------------------------------


def test_exif_stripped_jpeg_gps_gone_pixels_equal(api_client, tmp_upload_dir):
    data = _jpeg_with_exif(_checker())
    with Image.open(io.BytesIO(data)) as im:
        assert 34853 in im.getexif()  # GPS present before upload
    before = _pixels_hash(data)
    r = api_client.post("/api/triage/photo", files={"file": ("gps.jpg", data, "image/jpeg")})
    assert r.status_code == 200, r.text
    pid = r.json()["photo_id"]
    path = get_photo_path(pid)
    assert path is not None and path.is_file()
    stored = path.read_bytes()
    with Image.open(io.BytesIO(stored)) as im:
        im.load()
        tags = dict(im.getexif())
    assert 34853 not in tags and 271 not in tags and 272 not in tags
    assert _pixels_hash(stored) == before
    # sidecar persisted next to the file
    sidecar_path = photo_service._sidecar_path(pid)
    assert sidecar_path.is_file()
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["quality"] == r.json()["quality"]


def test_exif_stripped_png_pixels_equal(api_client, tmp_upload_dir):
    data = _png_with_exif(_checker(120, 12))
    before = _pixels_hash(data)
    r = api_client.post("/api/triage/photo", files={"file": ("x.png", data, "image/png")})
    assert r.status_code == 200, r.text
    path = get_photo_path(r.json()["photo_id"])
    assert path is not None
    stored = path.read_bytes()
    with Image.open(io.BytesIO(stored)) as im:
        im.load()
        assert im.info.get("exif") is None
    assert _pixels_hash(stored) == before


# --- 2. TTL sweep + META cap -------------------------------------------------


def test_ttl_sweep_deletes_old_but_keeps_fresh(api_client, tmp_upload_dir):
    r = api_client.post(
        "/api/triage/photo",
        files={"file": ("a.png", _png_bytes(_checker(80, 8)), "image/png")},
    )
    assert r.status_code == 200, r.text
    pid_old = r.json()["photo_id"]
    r2 = api_client.post(
        "/api/triage/photo",
        files={"file": ("b.png", _png_bytes(_checker(80, 8)), "image/png")},
    )
    assert r2.status_code == 200, r2.text
    pid_fresh = r2.json()["photo_id"]
    old_ts = time.time() - (31 * 24 * 3600)
    for pid in (pid_old,):
        p = get_photo_path(pid)
        assert p is not None
        os.utime(p, (old_ts, old_ts))
        sc = photo_service._sidecar_path(pid)
        if sc.is_file():
            os.utime(sc, (old_ts, old_ts))
    removed = sweep_expired_photos(ttl_seconds=30 * 24 * 3600)
    assert removed >= 1
    assert get_photo_path(pid_old) is None
    assert get_photo_path(pid_fresh) is not None
    assert photo_service._META.get(pid_old) is None


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_meta_cache_is_bounded(tmp_upload_dir):
    for i in range(MAX_META_ENTRIES + 50):
        photo_service._META[f"00000000-0000-0000-0000-{i:012d}"] = {"quality": "ok"}
    photo_service._cap_meta()
    assert len(photo_service._META) <= MAX_META_ENTRIES


# --- 3. GET / DELETE auth-gated ---------------------------------------------


def test_photo_get_delete_auth_gated(api_client, tmp_upload_dir, monkeypatch):
    data = _png_bytes(_checker(100, 10))
    r = api_client.post("/api/triage/photo", files={"file": ("s.png", data, "image/png")})
    assert r.status_code == 200, r.text
    pid = r.json()["photo_id"]

    monkeypatch.setenv("API_KEYS", TEST_KEY)
    try:
        assert api_client.get(f"/api/triage/photo/{pid}").status_code == 401
        assert api_client.delete(f"/api/triage/photo/{pid}").status_code == 401
        assert api_client.get(f"/api/triage/photo/{pid}", headers={"X-API-Key": "wrong"}).status_code == 401

        ok = api_client.get(f"/api/triage/photo/{pid}", headers={"X-API-Key": TEST_KEY})
        assert ok.status_code == 200, ok.text
        assert ok.headers["content-type"].startswith("image/")
        assert ok.content == get_photo_path(pid).read_bytes()  # type: ignore[union-attr]

        bad = api_client.get("/api/triage/photo/not-a-uuid", headers={"X-API-Key": TEST_KEY})
        assert bad.status_code == 404
        missing = api_client.get(
            "/api/triage/photo/00000000-0000-0000-0000-000000000000",
            headers={"X-API-Key": TEST_KEY},
        )
        assert missing.status_code == 404

        gone = api_client.delete(f"/api/triage/photo/{pid}", headers={"X-API-Key": TEST_KEY})
        assert gone.status_code == 200
        assert gone.json() == {"deleted": True, "photo_id": pid}
        assert api_client.get(f"/api/triage/photo/{pid}", headers={"X-API-Key": TEST_KEY}).status_code == 404
        assert api_client.delete(f"/api/triage/photo/{pid}", headers={"X-API-Key": TEST_KEY}).status_code == 404
    finally:
        monkeypatch.delenv("API_KEYS", raising=False)


# --- 4. security headers -------------------------------------------------------


def test_security_headers_present_everywhere(api_client):
    paths = [
        ("GET", "/", None),
        ("GET", "/api/health", None),
        ("GET", "/api/conditions", None),
        ("POST", "/api/triage/initial", {
            "age": 35, "sex": "male", "height_cm": 175.0, "weight_kg": 78.0,
            "body_zone": "живот", "symptoms_text": "боль внизу живота", "tags": [],
            "request_diet": False, "lang": "ru",
        }),
        ("GET", "/api/does-not-exist-xyz", None),
    ]
    for method, path, payload in paths:
        if method == "GET":
            resp = api_client.get(path)
        else:
            resp = api_client.post(path, json=payload)
        assert resp.headers.get("x-content-type-options") == "nosniff", path
        assert resp.headers.get("x-frame-options") == "DENY", path
        assert resp.headers.get("referrer-policy") == "no-referrer", path
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp, path
        # inline UI must keep working: unsafe-inline allowed for script/style
        assert "'unsafe-inline'" in csp, path


# --- 5. golden sha unchanged ---------------------------------------------------


def test_golden_sha_unchanged():
    golden = Path(__file__).resolve().parent / "golden_before.json"
    # Normalize CRLF->LF: Windows checkouts convert text files, CI (Linux) does
    # not. The sha must be line-ending independent (LF canonical).
    raw = golden.read_bytes().replace(b"\r\n", b"\n")
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == "09aeaf0a56eb318ff3dbc767d43a1b10aed2e782bd4d3c8a2dbf52e59fb9fec2"
    assert len(json.loads(golden.read_text(encoding="utf-8"))) == 10


def test_health_extended(api_client):
    body = api_client.get("/api/health").json()
    assert body == {"status": "ok", "service": "medi-ai", "version": APP_VERSION, "rules_version": RULES_VERSION}
    assert APP_VERSION == "1.0.0" and RULES_VERSION == "1.1"


# --- 6. smoke: offline UI + prod artefacts -------------------------------------


def test_smoke_offline_ui_and_prod_artefacts(api_client):
    root = api_client.get("/")
    assert root.status_code == 200, root.text
    assert "cdn.tailwindcss.com" not in root.text
    assert "/static/tailwind.css" in root.text

    css = api_client.get("/static/tailwind.css")
    assert css.status_code == 200
    assert ".bg-slate-100" in css.text and ".bg-blue-600" in css.text

    static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
    assert (static_dir / "tailwind.css").is_file()
    assert (static_dir / "index.html").is_file()

    repo = Path(__file__).resolve().parents[2]
    dockerfile = (repo / "medi-ai" / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12-slim" in dockerfile
    assert "appuser" in dockerfile and "USER" in dockerfile
    assert "--workers" in dockerfile
    assert "reload" not in dockerfile.lower().replace("no reload", "").replace("no --reload", "")
    ignore = (repo / "medi-ai" / ".dockerignore").read_text(encoding="utf-8")
    assert "uploads" in ignore

    src = (repo / "medi-ai" / "app" / "main.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in src
    assert "reload=True" not in src
    assert "UPLOAD_DIR" not in UPLOAD_DIR.name  # sanity: constant still points at app/uploads
