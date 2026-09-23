"""TASK-011 i18n dedup: resolver/mapper parity, catalog completeness, freeze parity."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import triage_engine
from app.domain import questions as questions_mod
from app.domain.catalog import get_conditions_catalog
from app.domain.questions import generate_initial_questions
from app.domain.rules import (
    _norm_lang,
    bmi_category,
    normalize_zone,
)
from app.domain.rules import (
    normalize_answer as rules_normalize_answer,
)
from app.i18n import LIST_MESSAGES, MESSAGES, normalize_answer, resolve_lang
from app.main import _resolve_lang
from app.schemas import (
    SportPlanRequest,
    TriageAnswer,
    TriageFinalRequest,
    TriageInitialRequest,
    map_lang,
    map_localized_answer,
)
from app.services.triage_service import _text as service_text
from app.sport_engine import _lang_of, build_sport_plan
from app.triage_engine import evaluate_final

FREEZE = Path(__file__).resolve().parent / "freeze_011_before.json"

LANG_CASES = ["ru", "en", "kz", "xx", None, "", "EN", "  kz  "]


def _sport_req(lang):
    return SimpleNamespace(lang=lang)


@pytest.mark.parametrize("inp", LANG_CASES)
def test_resolver_parity_all_aliases(inp):
    expected = resolve_lang(inp)
    assert _resolve_lang(inp) == expected
    assert map_lang(inp) == expected
    assert _norm_lang(inp) == expected
    assert _lang_of(_sport_req(inp)) == expected
    # contract: known langs pass through, everything else -> ru
    norm = (inp.strip().lower() if isinstance(inp, str) else "")
    assert expected == (norm if norm in ("ru", "en", "kz") else "ru")


@pytest.mark.parametrize(
    "raw,canon",
    [
        ("yes", "yes"), ("no", "no"), ("unsure", "unsure"),
        ("Да", "yes"), ("да, есть боль", "yes"), ("YES", "yes"),
        ("Нет", "no"), ("NO", "no"), ("нету", "no"),
        ("Не уверен(а)", "unsure"), ("не знаю", "unsure"), ("Not sure", "unsure"),
        ("Иә", "yes"), ("Жоқ", "no"), ("Сенімді емеспін", "unsure"),
        ("бар", "yes"), ("болады", "yes"), ("жок", "no"),
    ],
)
def test_answer_mapper_parity(raw, canon):
    assert normalize_answer(raw) == canon
    assert map_localized_answer(raw) == canon
    assert rules_normalize_answer(raw) == canon


@pytest.mark.parametrize("bad", ["maybe", "да нет", "", "123", "possibly", "иногда", "no да", "yes нет"])
def test_answer_mapper_rejects_parity(bad):
    for fn in (normalize_answer, map_localized_answer, rules_normalize_answer):
        with pytest.raises(ValueError):
            fn(bad)


def test_text_single_source():
    assert questions_mod._text is service_text


def test_shim_all_public_only():
    assert all(not name.startswith("_") for name in triage_engine.__all__)
    assert "resolve_lang" in triage_engine.__all__
    assert "MESSAGES" in triage_engine.__all__
    # dropped from shim: twin _text import (F401 fix) and other privates
    assert "_text" not in triage_engine.__all__
    assert not hasattr(triage_engine, "_text")
    assert not hasattr(triage_engine, "_norm_lang")
    # legacy private import still resolvable (explicit re-export for committed tests)
    assert callable(triage_engine._keyword_score)
    # canonical locations for the dropped aliases
    from app.domain.rules import _norm_lang as rules_norm_lang

    assert callable(rules_norm_lang)


def test_messages_cover_all_langs():
    for key, per_lang in MESSAGES.items():
        assert set(per_lang) == {"ru", "en", "kz"}, key
        assert all(isinstance(v, str) and v for v in per_lang.values()), key
    for key, per_lang in LIST_MESSAGES.items():
        assert set(per_lang) == {"ru", "en", "kz"}, key
        assert all(isinstance(v, list) and v for v in per_lang.values()), key


def test_message_templates_format_cleanly():
    assert MESSAGES["prob_gen_obesity_reason"]["ru"].format(bmi=22.9) == "ИМТ 22.9"
    assert MESSAGES["act_red_5"]["en"].format(see_doctor="X") == "5. After stabilization — urgently to: X."
    top_line = MESSAGES["act_top_line"]["kz"].format(band="орташа", name="N", icd="I10")
    assert "орташа" in top_line and "N (I10)" in top_line


@pytest.mark.parametrize("z", ["throat", "THROAT", "горло", "шея", "throat pain", "тамак", "тамақ"])
def test_normalize_zone_table_contract(z):
    assert normalize_zone(z) == "head"


def _ser(res):
    out = {}
    for k, v in res.items():
        if hasattr(v, "model_dump"):
            out[k] = v.model_dump()
        elif isinstance(v, list) and v and hasattr(v[0], "model_dump"):
            out[k] = [x.model_dump() for x in v]
        else:
            out[k] = v
    return out


# Mirrors medi-ai/tests/freeze_011.py case order (inputs not stored in the snapshot).
FINAL_CASES = [
    ("chest", "боль за грудиной давящая, холодный пот", ["Да", "Да", "Нет"], "ru", False, 70.0),
    ("chest", "pressing chest pain, cold sweat", ["yes", "yes", "no"], "en", False, 70.0),
    ("chest", "төс артындағы ауырсыну, суық тер", ["Иә", "Иә", "Жоқ"], "kz", False, 70.0),
    ("abdomen", "боль справа внизу живота, температура", ["Да", "Да", "Да"], "ru", False, 70.0),
    ("abdomen", "right lower abdominal pain, fever", ["yes", "yes", "no"], "en", False, 70.0),
    ("abdomen", "оң жақ төменгі іш ауырсынуы, қызба", ["Иә", "Жоқ", "Жоқ"], "kz", False, 70.0),
    ("head", "перекос лица, нарушение речи", ["Да", "Нет", "Нет"], "ru", False, 70.0),
    ("head", "face droop, speech problem", ["yes", "no", "no"], "en", False, 70.0),
    ("head", "бет қисаюы", ["Иә", "Жоқ", "Жоқ"], "kz", False, 70.0),
    ("skin", "покраснение распространяется, гной", ["Да", "Нет", "Нет"], "ru", False, 70.0),
    ("skin", "redness spreading fast, pus", ["yes", "no", "unsure"], "en", False, 70.0),
    ("limb", "упал, болит нога", ["Нет", "Нет", "Нет"], "ru", False, 70.0),
    ("limb", "fell, leg hurts", ["no", "no", "no"], "en", False, 70.0),
    ("general", "температура 39, озноб", ["Не уверен(а)", "Нет", "Нет"], "ru", False, 70.0),
    ("general", "fever, chills", ["unsure", "no", "no"], "en", False, 70.0),
    ("general", "қызба, қалтырау", ["Жоқ", "Жоқ", "Жоқ"], "kz", False, 70.0),
    ("abdomen", "черный стул, слабость", ["Нет", "Нет", "Нет"], "ru", False, 70.0),
    ("abdomen", "black stool, weakness", ["no", "no", "no"], "en", False, 70.0),
    ("general", "жажда, частое мочеиспускание", ["Нет", "Нет", "Нет"], "ru", True, 95.0),
    ("general", "thirst, frequent urination", ["no", "no", "no"], "en", True, 95.0),
    ("general", "шөлдеу", ["Жоқ", "Жоқ", "Жоқ"], "kz", True, 95.0),
    ("general", "mild headache", ["no", "no", "no"], "en", False, 70.0),
]


def test_freeze_parity_after_dedup():
    """Full before/after parity: recompute the TASK-011 freeze snapshot and compare."""
    snap = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert len(snap["final"]) == len(FINAL_CASES)

    for (zone, text, answers, lang, diet, weight), entry in zip(FINAL_CASES, snap["final"]):
        assert entry["zone"] == zone and entry["lang"] == lang and entry["text"] == text
        ans = [TriageAnswer(question_id=f"q{i + 1}", answer=a) for i, a in enumerate(answers)]
        req = TriageFinalRequest(
            age=30, sex="male", height_cm=175, weight_kg=weight,
            body_zone=zone, symptoms_text=text, tags=[],
            request_diet=diet, answers=ans, lang=lang,
        )
        assert _ser(evaluate_final(req)) == entry["result"]

    idx = 0
    for lang in ("ru", "en", "kz"):
        for zone in ("chest", "abdomen", "head", "skin", "limb", "general"):
            entry = snap["initial"][idx]
            idx += 1
            assert entry["lang"] == lang and entry["zone"] == zone
            req = TriageInitialRequest(
                age=30, sex="male", height_cm=175, weight_kg=70, body_zone=zone,
                symptoms_text="test symptom", tags=[], request_diet=False, lang=lang,
            )
            assert [q.model_dump() for q in generate_initial_questions(req)] == entry["qs"]

    for lang in ("ru", "en", "kz", "xx"):
        cur = get_conditions_catalog(lang)
        assert {k: [c.model_dump() for c in v] for k, v in cur.items()} == snap["catalog"][lang]

    idx = 0
    for lang in ("ru", "en", "kz"):
        for goal in ("lose", "gain", "strength", "endurance", "maintain"):
            entry = snap["sport"][idx]
            idx += 1
            assert entry["lang"] == lang and entry["goal"] == goal
            req = SportPlanRequest(
                age=30, sex="male", height_cm=175, weight_kg=80, goal=goal,
                activity_level="light", contraindications=[], lang=lang,
            )
            assert build_sport_plan(req) == entry["plan"]

    idx = 0
    for lang in ("ru", "en", "kz", "xx", None):
        for bmi in (17.0, 22.0, 27.0, 32.0, 37.0, 42.0):
            entry = snap["bmi"][idx]
            idx += 1
            assert bmi_category(bmi, lang) == entry["cat"]

    for entry in snap["zone"]:
        assert normalize_zone(entry["in"]) == entry["out"]
