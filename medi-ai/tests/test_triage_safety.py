"""Safety tests for TASK-002: scoring word-boundaries + fasting in any zone."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import TriageAnswer, TriageFinalRequest, TriageInitialRequest
from app.triage_engine import (
    _keyword_score,
    evaluate_final,
    generate_initial_questions,
    normalize_zone,
    triage_level_from_score,
)


def _initial(zone: str, text: str = "test symptom", lang: str = "ru") -> TriageInitialRequest:
    return TriageInitialRequest(
        age=30,
        sex="male",
        height_cm=175.0,
        weight_kg=70.0,
        body_zone=zone,
        symptoms_text=text,
        tags=[],
        request_diet=False,
        lang=lang,  # type: ignore[arg-type]
    )


def _final(zone: str, text: str, lang: str = "ru") -> TriageFinalRequest:
    no = [TriageAnswer(question_id=f"q{i}", answer="Нет") for i in range(1, 4)]
    return TriageFinalRequest(
        age=30,
        sex="male",
        height_cm=175.0,
        weight_kg=70.0,
        body_zone=zone,
        symptoms_text=text,
        tags=[],
        request_diet=False,
        answers=no,
        lang=lang,  # type: ignore[arg-type]
    )


# 1. 6 zones initial questions: exactly 3 each.
@pytest.mark.parametrize("zone", ["chest", "abdomen", "head", "skin", "limb", "general"])
def test_initial_questions_three_per_zone(zone: str):
    req = _initial(zone, text="боль и дискомфорт")
    qs = generate_initial_questions(req)
    assert len(qs) == 3
    for q in qs:
        assert q.id and q.text and q.reason
        assert len(q.options) == 3


# 2. bleed-in-every-zone → fasting (diet.allowed=false, strict regime).
BLEED_SIGNALS = [
    "мелена",
    "черный стул",
    "рвота кофейной гущей",
    "кровотечение",
    "bleeding",
    "black stool",
    "coffee-ground vomit",
    "қара нәжіс",
]

ZONES = ["chest", "abdomen", "head", "skin", "limb", "general"]


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("signal", BLEED_SIGNALS)
def test_bleed_in_every_zone_forces_fasting(zone: str, signal: str):
    req = _final(zone, f"жалобы: {signal}, слабость")
    res = evaluate_final(req)
    assert res["diet"].allowed is False
    regime = res["diet"].regime + " " + res["diet"].reason + " " + (res["diet"].warning or "")
    assert any(k in regime for k in ("ГОЛОД", "FASTING", "АШТЫҚ"))


def test_bleed_outside_abdomen_no_food():
    # regression: bleeding in head zone must still fast (old code allowed food)
    req = _final("head", "головная боль и черный стул, слабость")
    res = evaluate_final(req)
    assert res["diet"].allowed is False


# 3. normalize_zone('throat') → 'general' (no dedicated throat zone).
def test_normalize_zone_throat():
    assert normalize_zone("throat") == "general"
    assert normalize_zone("THROAT") == "general"


# 4. thresholds triage_engine.py:291-298
@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "GREEN"),
        (25, "GREEN"),
        (25.1, "YELLOW"),
        (60, "YELLOW"),
        (60.1, "ORANGE"),
        (85, "ORANGE"),
        (85.1, "RED"),
        (100, "RED"),
    ],
)
def test_triage_thresholds(score: float, expected: str):
    assert triage_level_from_score(score) == expected


# 5. breakfast != stroke (fast as standalone token only).
def test_breakfast_not_stroke():
    score, flags = _keyword_score("i had breakfast with eggs and coffee")
    assert "неврологический красный флаг (FAST)" not in flags
    assert score < 42
    # full pipeline stays low
    res = evaluate_final(_final("head", "I had breakfast with eggs"))
    assert "неврологический красный флаг (FAST)" not in res["_debug_reasons"]
    assert res["risk_score"] <= 25


def test_fast_standalone_is_stroke():
    score, flags = _keyword_score("FAST: face droop, arm weakness, speech problem")
    assert "неврологический красный флаг (FAST)" in flags
    assert score >= 42


# 6. 139/9 != severity (39 only standalone / температура 39|40, 38.5).
def test_bp_139_9_not_severity():
    score, flags = _keyword_score("давление 139/9, немного болит голова")
    assert "системная тяжесть" not in flags
    score2, flags2 = _keyword_score("BP 139/9 headache")
    assert "системная тяжесть" not in flags2


def test_temperature_39_is_severity():
    score, flags = _keyword_score("температура 39, озноб")
    assert "системная тяжесть" in flags
    assert score >= 25


def test_temperature_38_5_is_severity():
    score, flags = _keyword_score("температура 38.5 держится второй день")
    assert "системная тяжесть" in flags
