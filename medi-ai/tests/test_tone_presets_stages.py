"""TASK-006 tone + presets + honest staged UX (API-level where possible).

- Presets (mirror of index.html PRESETS): each must build a valid
  TriageInitialRequest and return exactly 3 questions from /api/triage/initial.
- Throat preset uses zone 'голова' (frontend mapping горло->голова);
  backend normalize_zone('горло'/'throat') == 'head' is asserted.
- One-by-one: answers collected sequentially assemble to a valid final;
  <3 answers must 422, 3 answers must 200 with breakdown+version.
- Frontend static guards: steps indicator, one-by-one renderer, framing
  block (ru/en/kz x cold/chronic/syndrome/redflag), presets row, no fake
  timers (setTimeout/setInterval), no sycophantic/alarmist copy.
- Scoring/thresholds untouched (no diet/sport/CI changes here).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.main import app
from app.schemas import TriageInitialRequest
from app.triage_engine import normalize_zone
from fastapi.testclient import TestClient

INDEX_HTML = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"

# Mirror of frontend PRESETS (zone/text/tags) in index.html.
PRESETS = {
    "throat-fever": {"zone": "голова", "text": "Болит горло, боль при глотании, температура 38.2, слабость второй день",
                     "tags": ["боль в горле", "лихорадка"], "canon": "head"},
    "chest-press": {"zone": "грудь", "text": "Давящая боль за грудиной, отдаёт в левую руку, холодный пот, одышка",
                    "tags": ["острая боль", "одышка"], "canon": "chest"},
    "abdomen-rl": {"zone": "живот", "text": "Боль внизу живота справа, усиливается при ходьбе и кашле, тошнота, температура 37.8",
                   "tags": ["острая боль", "тошнота"], "canon": "abdomen"},
    "migraine": {"zone": "голова", "text": "Пульсирующая головная боль с одной стороны, тошнота, раздражают свет и звук",
                 "tags": ["острая боль", "тошнота"], "canon": "head"},
    "rash": {"zone": "кожа", "text": "Красная сыпь быстро распространяется, зуд, отёк, поднялась температура",
             "tags": ["сыпь", "лихорадка"], "canon": "skin"},
    "back-numb": {"zone": "конечности", "text": "Боль в пояснице отдаёт в ногу, онемение и мурашки",
                  "tags": ["острая боль"], "canon": "limb"},
}


def _initial_payload(p):
    return {"age": 35, "sex": "male", "height_cm": 175, "weight_kg": 78,
            "body_zone": p["zone"], "symptoms_text": p["text"],
            "tags": p["tags"], "request_diet": False, "lang": "ru"}


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_preset_zone_mapping(key):
    p = PRESETS[key]
    assert normalize_zone(p["zone"]) == p["canon"], key
    # frontend contract: throat complaints use head zone (no dedicated throat zone)
    if key == "throat-fever":
        assert normalize_zone("горло") == "head"
        assert normalize_zone("throat") == "head"


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_preset_produces_valid_initial_payload(key):
    p = PRESETS[key]
    req = TriageInitialRequest(**_initial_payload(p))  # pydantic validation
    assert len(req.symptoms_text) >= 3
    c = TestClient(app)
    r = c.post("/api/triage/initial", json=_initial_payload(p))
    assert r.status_code == 200, f"{key}: {r.text}"
    assert len(r.json()["questions"]) == 3, key


def test_one_by_one_answers_assemble_to_valid_final():
    c = TestClient(app)
    p = PRESETS["abdomen-rl"]
    init = c.post("/api/triage/initial", json=_initial_payload(p)).json()
    qids = [q["id"] for q in init["questions"]]
    assert len(qids) == 3
    base = dict(_initial_payload(p))

    # staged: 1 answer only -> 422 (contract: exactly 3)
    r1 = c.post("/api/triage/final", json={**base, "answers": [
        {"question_id": qids[0], "answer": "no"}]})
    assert r1.status_code == 422

    # staged: 2 answers -> 422
    r2 = c.post("/api/triage/final", json={**base, "answers": [
        {"question_id": qids[0], "answer": "no"},
        {"question_id": qids[1], "answer": "no"}]})
    assert r2.status_code == 422

    # staged: one-by-one accumulation to 3 -> 200, transparency intact
    answers = [{"question_id": qids[0], "answer": "no"},
               {"question_id": qids[1], "answer": "no"},
               {"question_id": qids[2], "answer": "no"}]
    r3 = c.post("/api/triage/final", json={**base, "answers": answers})
    assert r3.status_code == 200, r3.text
    d = r3.json()
    assert d["triage_level"] in ("GREEN", "YELLOW", "ORANGE", "RED")
    assert d["rules_version"] == "1.1" and isinstance(d["score_breakdown"], list)
    assert len(d["probable_conditions"]) > 0


def _html():
    return INDEX_HTML.read_text(encoding="utf-8")


def test_frontend_stages_and_presets_present():
    h = _html()
    assert 'id="presetRow"' in h
    for key in PRESETS:
        assert f'data-preset="{key}"' in h, f"missing preset button {key}"
    assert 'id="steps"' in h and h.count('data-step=') >= 3
    assert 'id="stepQpos"' in h
    assert "renderOneQuestion" in h and "Вопрос ${idx + 1} из" in h
    assert 'id="framing"' in h and "framingText" in h
    assert "FRAMING" in h
    # skeleton only around real fetch, How-we-counted kept
    assert "animate-pulse" in h and "Как мы посчитали" in h


def test_frontend_no_fake_timers_or_deps():
    h = _html()
    assert "setTimeout" not in h and "setInterval" not in h
    assert "three" not in h.lower()


def test_frontend_framing_covers_langs_and_kinds():
    h = _html()
    for lang in ("ru:", "en:", "kz:"):
        assert lang in h, f"missing FRAMING lang {lang}"
    for kind in ("cold:", "chronic:", "syndrome:", "redflag:"):
        assert kind in h, f"missing framing kind {kind}"
    assert "framingKind" in h


BANNED_SYCOPHANTIC = ["всё будет хорошо", "все будет хорошо", "everything will be fine",
                      "не волнуйтесь, всё пройдёт", "MediAI думает", "Готово (предварительная"]


def test_frontend_tone_neutral_no_sycophancy():
    h = _html()
    low = h.lower()
    for b in BANNED_SYCOPHANTIC:
        assert b.lower() not in low, f"banned copy present: {b}"
    # neutral realist markers must exist
    assert "не диагноз" in low
    assert "эвристика" in low
    assert "Запрос выполняется" in h
    assert "Предварительная оценка (не диагноз)" in h


def test_frontend_presets_use_state_tags_flow():
    h = _html()
    assert "state.tags.clear()" in h
    assert "syncTagButtons" in h
    assert re.search(r"PRESETS\s*=\s*\{", h)
