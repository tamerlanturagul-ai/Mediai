"""Photo upload envelope tests (TASK-008, decision B4-variant-1).

Photo is an envelope for the doctor, NEVER a diagnostic signal:
upload returns {photo_id, quality, hint} (Pillow-only heuristics, no ML),
and final results carry photos_attached WITHOUT changing score/conditions/diet.
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.services.photo_service import MAX_PHOTO_BYTES, UPLOAD_DIR

client = TestClient(app)


@pytest.fixture()
def clean_uploads():
    before = set(UPLOAD_DIR.glob("*")) if UPLOAD_DIR.is_dir() else set()
    yield
    if UPLOAD_DIR.is_dir():
        for p in UPLOAD_DIR.glob("*"):
            if p not in before and p.is_file():
                p.unlink()


def _checker(size=200, cell=10) -> Image.Image:
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(30, 30, 30))
    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload(data: bytes, filename: str, ctype: str):
    return client.post(
        "/api/triage/photo",
        files={"file": (filename, data, ctype)},
    )


def _final_payload(**extra):
    base = {
        "age": 35, "sex": "male", "height_cm": 175.0, "weight_kg": 78.0,
        "body_zone": "живот", "symptoms_text": "боль внизу живота справа, тошнота",
        "tags": ["острая боль"], "request_diet": False, "lang": "ru",
        "answers": [
            {"question_id": "q1", "answer": "no"},
            {"question_id": "q2", "answer": "no"},
            {"question_id": "q3", "answer": "no"},
        ],
    }
    base.update(extra)
    return base


def test_upload_valid_image_ok(clean_uploads):
    r = _upload(_png_bytes(_checker()), "skin.png", "image/png")
    assert r.status_code == 200, r.text
    body = r.json()
    uuid.UUID(body["photo_id"])  # valid UUID
    assert body["quality"] == "ok"
    assert body["hint"]
    stored = list(UPLOAD_DIR.glob(f"{body['photo_id']}.*"))
    assert len(stored) == 1  # UUID filename under medi-ai/uploads/


def test_upload_dark_image(clean_uploads):
    dark = Image.new("RGB", (200, 200), (10, 10, 10))
    r = _upload(_png_bytes(dark), "dark.png", "image/png")
    assert r.status_code == 200, r.text
    assert r.json()["quality"] == "too_dark"


def test_upload_blurry_image(clean_uploads):
    blurry = _checker().filter(ImageFilter.GaussianBlur(radius=8))
    r = _upload(_png_bytes(blurry), "blur.png", "image/png")
    assert r.status_code == 200, r.text
    assert r.json()["quality"] == "too_blurry"


def test_upload_wrong_type_rejected(clean_uploads):
    r = _upload(b"not an image at all", "note.txt", "text/plain")
    assert r.status_code in (400, 422), r.text


def test_upload_corrupt_image_rejected(clean_uploads):
    r = _upload(b"\x89PNG\r\nnot really png", "fake.png", "image/png")
    assert r.status_code in (400, 422), r.text


def test_upload_oversize_rejected(clean_uploads):
    big = Image.frombytes("RGB", (1700, 1700), os.urandom(1700 * 1700 * 3))
    data = _png_bytes(big)
    assert len(data) > MAX_PHOTO_BYTES  # genuinely over 8 MB
    r = _upload(data, "big.png", "image/png")
    assert r.status_code == 413, r.text


def test_final_bad_photo_id_format(clean_uploads):
    r = client.post("/api/triage/final", json=_final_payload(photo_ids=["not-a-uuid"]))
    assert r.status_code == 422, r.text


def test_final_unknown_photo_id(clean_uploads):
    r = client.post("/api/triage/final", json=_final_payload(photo_ids=[str(uuid.uuid4())]))
    assert r.status_code == 422, r.text


def test_final_photo_cap_of_3(clean_uploads):
    up = _upload(_png_bytes(_checker()), "skin.png", "image/png")
    pid = up.json()["photo_id"]
    r = client.post("/api/triage/final", json=_final_payload(photo_ids=[pid] * 4))
    assert r.status_code == 422, r.text


def test_golden_identical_with_and_without_photos(clean_uploads):
    """Same symptoms +/- photo -> identical score/level/ICDs/diet."""
    up = _upload(_png_bytes(_checker()), "skin.png", "image/png")
    assert up.status_code == 200, up.text
    pid = up.json()["photo_id"]

    plain = client.post("/api/triage/final", json=_final_payload()).json()
    with_photo = client.post("/api/triage/final", json=_final_payload(photo_ids=[pid])).json()

    assert with_photo["risk_score"] == plain["risk_score"]
    assert with_photo["triage_level"] == plain["triage_level"]
    assert [(c["name"], c["icd10"], c["probability"]) for c in with_photo["probable_conditions"]] == [
        (c["name"], c["icd10"], c["probability"]) for c in plain["probable_conditions"]
    ]
    assert with_photo["diet"] == plain["diet"]
    # envelope carried "for the doctor"
    assert with_photo["photos_attached"] == [{"photo_id": pid, "quality": "ok"}]
    assert plain["photos_attached"] == []
