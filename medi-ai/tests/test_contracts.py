"""Contract tests for TASK-003: Answer Literal, CORS, throat mapping, lang consistency."""
from __future__ import annotations

import os

import pytest
from app.main import _resolve_lang, app
from app.schemas import TriageAnswer, TriageFinalRequest, TriageInitialRequest
from app.triage_engine import generate_initial_questions, normalize_zone
from fastapi.testclient import TestClient
from pydantic import ValidationError


def _initial(zone="chest", lang="ru"):
    return TriageInitialRequest(
        age=30, sex="male", height_cm=175.0, weight_kg=70.0,
        body_zone=zone, symptoms_text="боль и дискомфорт", tags=[],
        request_diet=False, lang=lang,
    )


def _final(answers, zone="chest", lang="ru"):
    ans = [TriageAnswer(question_id=f"q{i+1}", answer=a) for i, a in enumerate(answers)]
    return TriageFinalRequest(
        age=30, sex="male", height_cm=175.0, weight_kg=70.0,
        body_zone=zone, symptoms_text="боль и дискомфорт", tags=[],
        request_diet=False, answers=ans, lang=lang,
    )


# 1. Answer Literal accepts yes/no/unsure (+ localized mapping), rejects free text.
@pytest.mark.parametrize("raw,canon", [
    ("yes", "yes"), ("no", "no"), ("unsure", "unsure"),
    ("Да", "yes"), ("да, есть боль", "yes"), ("YES", "yes"),
    ("Нет", "no"), ("NO", "no"),
    ("Не уверен(а)", "unsure"), ("не знаю", "unsure"),
    ("Yes", "yes"), ("Not sure", "unsure"),
    ("Иә", "yes"), ("Жоқ", "no"), ("Сенімді емеспін", "unsure"),
])
def test_answer_mapping_accepts(raw, canon):
    a = TriageAnswer(question_id="q1", answer=raw)
    assert a.answer == canon


@pytest.mark.parametrize("bad", ["maybe", "да нет", "", "123", "possibly", "иногда"])
def test_answer_rejects_free_text(bad):
    with pytest.raises(ValidationError):
        TriageAnswer(question_id="q1", answer=bad)


# 2. CORS: no '*' with credentials.
def test_cors_no_star_with_credentials():
    # default (no env) must not be '*'
    from app import main as main_mod
    origins = main_mod._cors_origins()
    assert "*" not in origins
    # find CORSMiddleware options via app middleware stack
    for m in app.user_middleware:
        if "CORSMiddleware" in str(m.cls):
            opts = m.kwargs if hasattr(m, "kwargs") else m.options
            assert "*" not in opts.get("allow_origins", ["*"]) or opts.get("allow_credentials") is False
    # env override respected
    os.environ["CORS_ORIGINS"] = "https://example.com, https://app.example.com"
    try:
        assert main_mod._cors_origins() == ["https://example.com", "https://app.example.com"]
    finally:
        del os.environ["CORS_ORIGINS"]


def test_cors_headers_no_star():
    c = TestClient(app)
    r = c.options("/api/triage/final", headers={
        "Origin": "https://example.com",
        "Access-Control-Request-Method": "POST",
    })
    # star must never appear as allow-origin when credentials involved
    assert r.headers.get("access-control-allow-origin") != "*"


# 3. throat mapping -> head.
@pytest.mark.parametrize("z", ["throat", "THROAT", "горло", "Горло болит", "шея", "throat pain"])
def test_throat_maps_to_head(z):
    assert normalize_zone(z) == "head"


def test_throat_questions_use_head_bank():
    req = _initial("throat", "ru")
    qs = generate_initial_questions(req)
    assert len(qs) == 3
    # head bank ids start with neuro_
    assert qs[0].id.startswith("neuro_")


# 4. lang consistency: single helper, fallback to ru.
@pytest.mark.parametrize("inp,exp", [
    ("ru", "ru"), ("en", "en"), ("kz", "kz"),
    ("EN", "en"), ("xx", "ru"), ("", "ru"), (None, "ru"),
])
def test_resolve_lang_consistent(inp, exp):
    assert _resolve_lang(inp) == exp


def test_lang_consistent_across_routes():
    c = TestClient(app)
    # initial: unknown lang falls back to ru (no 422)
    r = c.post("/api/triage/initial", json={
        "age": 30, "sex": "male", "height_cm": 175, "weight_kg": 70,
        "body_zone": "chest", "symptoms_text": "боль в груди давит",
        "tags": [], "request_diet": False, "lang": "xx",
    })
    assert r.status_code == 200
    assert r.json()["lang"] == "ru"
    # final: same fallback
    r2 = c.post("/api/triage/final", json={
        "age": 30, "sex": "male", "height_cm": 175, "weight_kg": 70,
        "body_zone": "chest", "symptoms_text": "боль в груди давит",
        "tags": [], "request_diet": False, "lang": "xx",
        "answers": [
            {"question_id": "q1", "answer": "no"},
            {"question_id": "q2", "answer": "no"},
            {"question_id": "q3", "answer": "no"},
        ],
    })
    assert r2.status_code == 200
    assert r2.json()["lang"] == "ru"
    # conditions: same fallback
    r3 = c.get("/api/conditions", params={"lang": "xx"})
    assert r3.status_code == 200
    # en works everywhere
    r4 = c.post("/api/triage/initial", json={
        "age": 30, "sex": "male", "height_cm": 175, "weight_kg": 70,
        "body_zone": "chest", "symptoms_text": "chest pain pressing",
        "tags": [], "request_diet": False, "lang": "en",
    })
    assert r4.status_code == 200
    assert r4.json()["lang"] == "en"
    assert "Is the chest pain" in r4.json()["questions"][0]["text"]
