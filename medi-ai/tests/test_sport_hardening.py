"""TASK-007 sport hardening: BMR other-sex, BMI>=30 ban, PAR-Q gating, caps, EN/KZ parity."""
from __future__ import annotations

import re

import pytest
from app.main import app
from app.schemas import SportPlanRequest
from app.sport_engine import (
    _MIFFLIN_S_FEMALE,
    _MIFFLIN_S_MALE,
    _MIFFLIN_S_OTHER,
    _bmr_mifflin,
    build_sport_plan,
    parq_positive,
)
from fastapi.testclient import TestClient

LANGS = ["ru", "en", "kz"]

# Height 170 cm -> h^2 = 2.89: weights pin BMI 29.9 / 30.0 / 30.1 exactly.
BMI_CASES = [(86.4, 29.9, False), (86.7, 30.0, True), (87.0, 30.1, True)]

_BAN_MARKER = {"ru": "ИМТ ≥ 30", "en": "BMI ≥ 30", "kz": "ДСИ ≥ 30"}
_RUN_MARKER = {"ru": "пробежка", "en": "interval run", "kz": "интервалды жүгіру"}
_SWIM_MARKER = {"ru": "вместо бега", "en": "instead of running", "kz": "орнына жүзу/вело"}
_PARQ_WARN_MARKER = {"ru": "допуск врача", "en": "doctor clearance", "kz": "дәрігердің рұқсатын"}
_LOW_IMPACT_MARKERS = {
    "ru": ["Ходьба", "Плавание"],
    "en": ["Walking", "Swimming"],
    "kz": ["Жаяу жүру", "Жүзу"],
}
_HIGH_IMPACT_TOKENS = {
    "ru": ["пробежка", "прыжки", "интервальн"],
    "en": ["run", "jump", "interval"],
    "kz": ["жүгіру", "секіру", "интервал"],
}
_HONEST_MARKER = {"ru": "не гарантия", "en": "not a guarantee", "kz": "кепілдік емес"}

PARQ_BOOL_FLAGS = [
    "parq_chest_pain",
    "parq_dizziness",
    "parq_joint_problem",
    "parq_heart_condition",
    "parq_diabetes",
    "parq_age50_unsupervised",
]


def _req(weight_kg=70.0, lang="ru", goal="lose", **kw):
    base = {"age": 30, "sex": "male", "height_cm": 170.0, "weight_kg": weight_kg,
            "goal": goal, "activity_level": "light", "lang": lang}
    base.update(kw)
    return SportPlanRequest(**base)


def _first_float(text: str) -> float:
    m = re.search(r"([\d]+(?:\.[\d]+)?)", text)
    assert m, f"no number in tempo text: {text!r}"
    return float(m.group(1))


# 1. BMR other-sex: mean of Mifflin-St Jeor male/female constants, documented.
def test_bmr_other_constant_is_documented_mean():
    assert (_MIFFLIN_S_MALE, _MIFFLIN_S_FEMALE) == (5, -161)
    assert _MIFFLIN_S_OTHER == -78
    assert _MIFFLIN_S_OTHER == round((_MIFFLIN_S_MALE + _MIFFLIN_S_FEMALE) / 2)


def test_bmr_other_value_pinned():
    got = _bmr_mifflin("other", 70.0, 175.0, 30)
    assert got == round(10 * 70.0 + 6.25 * 175.0 - 5 * 30 - 78, 1)
    male = _bmr_mifflin("male", 70.0, 175.0, 30)
    female = _bmr_mifflin("female", 70.0, 175.0, 30)
    assert got == round((male + female) / 2, 1)


# 2. BMI boundary trio in all three langs.
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("weight,bmi,expect_ban", BMI_CASES)
def test_bmi_boundary_ban(lang, weight, bmi, expect_ban):
    plan = build_sport_plan(_req(weight, lang))
    assert plan["bmi"] == bmi
    contra_text = "\n".join(plan["contraindications"])
    warn_text = "\n".join(plan["warnings"])
    if expect_ban:
        assert _BAN_MARKER[lang] in contra_text
    else:
        assert "≥ 30" not in contra_text
        assert "≥ 30" not in warn_text


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("weight,bmi,expect_ban", BMI_CASES)
def test_bmi_boundary_training_swap(lang, weight, bmi, expect_ban):
    plan = build_sport_plan(_req(weight, lang, goal="lose"))
    training_text = "\n".join(plan["training_plan"])
    if expect_ban:
        assert _SWIM_MARKER[lang] in training_text
        assert _RUN_MARKER[lang] not in training_text
    else:
        assert _RUN_MARKER[lang] in training_text
        assert _SWIM_MARKER[lang] not in training_text


# 3. PAR-Q gating per lang.
def test_parq_defaults_negative():
    req = _req()
    assert parq_positive(req) is False
    plan = build_sport_plan(req)
    assert _PARQ_WARN_MARKER["ru"] not in "\n".join(plan["warnings"])
    assert _RUN_MARKER["ru"] in "\n".join(plan["training_plan"])


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("flag", PARQ_BOOL_FLAGS)
@pytest.mark.parametrize("goal", ["lose", "endurance"])
def test_parq_each_flag_forces_low_impact(lang, flag, goal):
    plan = build_sport_plan(_req(70.0, lang, goal, **{flag: True}))
    warn_text = "\n".join(plan["warnings"])
    training_text = "\n".join(plan["training_plan"])
    assert _PARQ_WARN_MARKER[lang] in warn_text
    for marker in _LOW_IMPACT_MARKERS[lang]:
        assert marker in training_text
    for token in _HIGH_IMPACT_TOKENS[lang]:
        assert token not in training_text


@pytest.mark.parametrize("lang", LANGS)
def test_parq_other_text_triggers(lang):
    plan = build_sport_plan(_req(70.0, lang, parq_other="knee surgery last year"))
    assert _PARQ_WARN_MARKER[lang] in "\n".join(plan["warnings"])
    for token in _HIGH_IMPACT_TOKENS[lang]:
        assert token not in "\n".join(plan["training_plan"])


def test_parq_other_blank_is_negative():
    assert parq_positive(_req(parq_other="   ")) is False


def test_parq_all_flags_at_once_ru():
    kw = {f: True for f in PARQ_BOOL_FLAGS}
    plan = build_sport_plan(_req(70.0, "ru", **kw))
    assert _PARQ_WARN_MARKER["ru"] in "\n".join(plan["warnings"])
    assert _RUN_MARKER["ru"] not in "\n".join(plan["training_plan"])


# 4. Realism caps pinned.
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("weight,expected", [(40.0, 0.4), (80.0, 0.6), (200.0, 1.0)])
def test_weekly_loss_clamp(lang, weight, expected):
    plan = build_sport_plan(_req(weight, lang, goal="lose"))
    assert _first_float(plan["weekly_tempo_kg"]) == expected


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("age,expected", [(25, 1.0), (65, 0.7)])
def test_monthly_gain_cap(lang, age, expected):
    req = _req(70.0, lang, goal="gain", age=age)
    plan = build_sport_plan(req)
    assert _first_float(plan["weekly_tempo_kg"]) == expected
    assert _first_float(plan["weekly_tempo_kg"]) <= 1.0


# Honest wording in every goal x lang.
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("goal", ["lose", "gain", "strength", "endurance", "maintain"])
def test_honest_wording_everywhere(lang, goal):
    plan = build_sport_plan(_req(70.0, lang, goal))
    assert _HONEST_MARKER[lang] in plan["timeline_text"]


# 5. EN/KZ parity with RU.
@pytest.mark.parametrize("goal", ["lose", "gain", "strength", "endurance", "maintain"])
def test_numeric_parity_across_langs(goal):
    plans = {lang: build_sport_plan(_req(70.0, lang, goal)) for lang in LANGS}
    for lang in ("en", "kz"):
        for key in ("bmi", "bmr_kcal", "tdee_kcal", "target_kcal", "timeline_weeks"):
            assert plans[lang][key] == plans["ru"][key], f"{key}: {lang} != ru"
    for lang in LANGS:
        assert plans[lang]["training_plan"] and plans[lang]["nutrition_hint"]
        assert _HONEST_MARKER[lang] in plans[lang]["timeline_text"]


def test_localized_not_copies():
    ru = build_sport_plan(_req(70.0, "ru"))
    en = build_sport_plan(_req(70.0, "en"))
    kz = build_sport_plan(_req(70.0, "kz"))
    assert "\n".join(ru["training_plan"]) != "\n".join(en["training_plan"])
    assert "\n".join(ru["training_plan"]) != "\n".join(kz["training_plan"])


def test_lang_fallback_to_ru():
    req = SportPlanRequest(age=30, sex="male", height_cm=170.0, weight_kg=70.0,
                           goal="lose", activity_level="light", lang="xx")
    assert req.lang == "ru"
    assert build_sport_plan(req)["lang"] == "ru"


def test_sport_endpoint_lang_echo():
    c = TestClient(app)
    for lang in LANGS:
        r = c.post("/api/sport/plan", json={
            "age": 30, "sex": "male", "height_cm": 170, "weight_kg": 70,
            "goal": "lose", "activity_level": "light",
            "contraindications": [], "lang": lang,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["lang"] == lang
        assert _HONEST_MARKER[lang] in body["timeline_text"]
