"""TASK-004 honest outputs: bands, breakdown+version, no % in actions, golden unchanged."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.rules import RULES_VERSION, likelihood_band, likelihood_label
from app.main import app
from app.schemas import TriageAnswer, TriageFinalRequest


def _final(zone="chest", text="боль и дискомфорт", answers=("no", "no", "no"), lang="ru",
           age=30, h=175.0, w=70.0, diet=False):
    ans = [TriageAnswer(question_id=f"q{i+1}", answer=a) for i, a in enumerate(answers)]
    return TriageFinalRequest(age=age, sex="male", height_cm=h, weight_kg=w,
        body_zone=zone, symptoms_text=text, tags=[], request_diet=diet,
        answers=ans, lang=lang)


# 1. bands mapping: <30 low, 30-60 medium, >60 high.
@pytest.mark.parametrize("prob,exp", [
    (0, "low"), (5, "low"), (29.9, "low"),
    (30, "medium"), (30.0, "medium"), (42, "medium"), (60, "medium"), (60.0, "medium"),
    (60.1, "high"), (65, "high"), (95, "high"),
])
def test_likelihood_band_thresholds(prob, exp):
    assert likelihood_band(prob) == exp


def test_likelihood_labels_per_lang():
    assert likelihood_label(20, "en") == "low"
    assert likelihood_label(50, "en") == "medium"
    assert likelihood_label(80, "en") == "high"
    assert likelihood_label(20, "ru") == "низкая"
    assert likelihood_label(50, "ru") == "средняя"
    assert likelihood_label(80, "ru") == "высокая"
    assert likelihood_label(20, "kz") == "төмен"
    assert likelihood_label(50, "kz") == "орташа"
    assert likelihood_label(80, "kz") == "жоғары"
    assert RULES_VERSION == "1.1"


# 2. breakdown + version present in final response (service + API).
def test_breakdown_and_version_service():
    from app.triage_engine import evaluate_final
    req = _final("chest", "боль за грудиной давящая, холодный пот", ("yes", "yes", "no"))
    res = evaluate_final(req)
    assert res["rules_version"] == "1.1"
    assert isinstance(res["score_breakdown"], list) and len(res["score_breakdown"]) > 0
    total = round(sum(b["points"] for b in res["score_breakdown"]), 1)
    assert total == res["risk_score"], f"breakdown sum {total} != risk {res['risk_score']}"
    for b in res["score_breakdown"]:
        assert "reason" in b and "points" in b and b["points"] > 0


def test_breakdown_and_version_api():
    c = TestClient(app)
    r = c.post("/api/triage/final", json={
        "age": 30, "sex": "male", "height_cm": 175, "weight_kg": 70,
        "body_zone": "chest", "symptoms_text": "боль за грудиной давящая",
        "tags": [], "request_diet": False, "lang": "ru",
        "answers": [{"question_id": "q1", "answer": "yes"},
                    {"question_id": "q2", "answer": "no"},
                    {"question_id": "q3", "answer": "no"}],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["rules_version"] == "1.1"
    assert isinstance(d["score_breakdown"], list) and len(d["score_breakdown"]) > 0
    # numeric probability kept for compat
    assert all("probability" in p for p in d["probable_conditions"])


# 3. no % in actions text (all langs x all levels), aspirin gate intact.
@pytest.mark.parametrize("lang", ["ru", "en", "kz"])
@pytest.mark.parametrize("zone,text,answers", [
    ("chest", "боль за грудиной давящая, холодный пот", ("yes", "yes", "yes")),  # RED
    ("chest", "боль за грудиной давящая, холодный пот", ("yes", "yes", "no")),   # ORANGE
    ("head", "головная боль давящая", ("no", "no", "no")),                       # YELLOW/GREEN
    ("limb", "упал, болит нога", ("no", "no", "no")),                            # GREEN
])
def test_no_percent_in_actions(lang, zone, text, answers):
    from app.triage_engine import evaluate_final
    req = _final(zone, text, answers, lang=lang)
    res = evaluate_final(req)
    joined = "\n".join(res["actions"])
    assert "%" not in joined, f"actions contain % [{lang}]: {joined}"
    assert "~" not in res["actions"][-1]
    last = res["actions"][-1].lower()
    if lang == "ru":
        assert "не диагноз" in last and "требуется очно" in last and "вероятность" in last
        assert "дифдиагноз" not in last.lower() or "не диагноз" in last
    elif lang == "en":
        assert "not a diagnosis" in last and "likelihood" in last
    else:
        assert "диагноз емес" in last


def test_aspirin_stays_dispatcher_gated():
    from app.triage_engine import evaluate_final
    # RED chest in each lang must contain gated aspirin line
    for lang, markers in [
        ("ru", ["аспирин", "только", "скорая одобрила"]),
        ("en", ["aspirin", "only", "dispatcher"]),
        ("kz", ["аспирин", "диспетчер"]),
    ]:
        req = _final("chest", "боль за грудиной давящая холодный пот", ("yes", "yes", "yes"), lang=lang)
        res = evaluate_final(req)
        assert res["triage_level"] == "RED"
        joined = "\n".join(res["actions"]).lower()
        for m in markers:
            assert m.lower() in joined, f"aspirin gate lost [{lang}]: missing {m}"


# 4. unknown-input golden unchanged (scoring untouched).
def test_unknown_input_golden_unchanged():
    golden = json.loads((Path(__file__).parent / "golden_before.json").read_text(encoding="utf-8"))
    from app.triage_engine import evaluate_final
    # nonsense/unknown input: breakfast case must stay GREEN / low risk (no FAST false-positive)
    req = _final("head", "I had breakfast with eggs", ("no", "no", "no"))
    res = evaluate_final(req)
    assert res["risk_score"] <= 25
    assert res["triage_level"] == "GREEN"
    # full numeric golden (except honest actions line) unchanged for all 10 cases
    from tests.test_golden_regression import CASES, _mk, _ser
    for (name, zone, text, answers, age, h, w, diet), g in zip(CASES, golden):
        cur = _ser(evaluate_final(_mk(zone, text, answers, age, h, w, diet)))
        exp = g["result"]
        assert cur["risk_score"] == exp["risk_score"], name
        assert cur["triage_level"] == exp["triage_level"], name
        assert [c["icd10"] for c in cur["probable_conditions"]] == [c["icd10"] for c in exp["probable_conditions"]], name
