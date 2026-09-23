"""Golden regression for TASK-003 split: 10 frozen evaluate_final outputs must match 1:1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import TriageAnswer, TriageFinalRequest
from app.triage_engine import evaluate_final

GOLDEN = Path(__file__).resolve().parent / "golden_before.json"

# Same 10 cases as freeze_golden.py (RU, no throat to avoid intentional contract diff).
CASES = [
    ("chest cardiac", "chest", "боль за грудиной давящая, холодный пот, нехватка воздуха", ["Да", "Да", "Нет"], 30, 175, 70, False),
    ("abdomen append", "abdomen", "боль справа внизу живота, миграция боли, температура, тошнота", ["Да", "Да", "Да"], 30, 175, 70, False),
    ("head stroke", "head", "перекос лица, онемела рука, нарушение речи", ["Да", "Нет", "Нет"], 30, 175, 70, False),
    ("skin spread", "skin", "покраснение быстро распространяется, лихорадка, гной", ["Да", "Нет", "Не уверен(а)"], 30, 175, 70, False),
    ("limb trauma", "limb", "упал, болит нога, могу опираться, онемения нет", ["Нет", "Нет", "Нет"], 30, 175, 70, False),
    ("general fever", "general", "температура 39, озноб, слабость", ["Не уверен(а)", "Нет", "Нет"], 30, 175, 70, False),
    ("abdomen bleed", "abdomen", "черный стул, слабость, рвота кофейной гущей", ["Нет", "Нет", "Нет"], 30, 175, 70, False),
    ("head bleed non-abdomen", "head", "головная боль и черный стул, слабость", ["Нет", "Нет", "Нет"], 30, 175, 70, False),
    ("head breakfast", "head", "I had breakfast with eggs", ["Нет", "Нет", "Нет"], 30, 175, 70, False),
    ("general obese-diet", "general", "жажда, частое мочеиспускание, лишний вес", ["Нет", "Нет", "Нет"], 30, 175, 95, True),
]


def _mk(zone, text, answers, age, height, weight, diet):
    ans = [TriageAnswer(question_id=f"q{i+1}", answer=a) for i, a in enumerate(answers)]
    return TriageFinalRequest(age=age, sex="male", height_cm=height, weight_kg=weight,
        body_zone=zone, symptoms_text=text, tags=[], request_diet=diet, answers=ans)


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


def test_golden_matches_before():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden) == 10
    for (name, zone, text, answers, age, h, w, diet), g in zip(CASES, golden):
        assert g["case"] == name
        req = _mk(zone, text, answers, age, h, w, diet)
        cur = _ser(evaluate_final(req))
        exp = g["result"]
        assert cur["risk_score"] == exp["risk_score"], f"{name} risk_score {cur['risk_score']} != {exp['risk_score']}"
        assert cur["triage_level"] == exp["triage_level"], f"{name} level"
        assert cur["bmi"] == exp["bmi"], f"{name} bmi"
        assert cur["bmi_category"] == exp["bmi_category"], f"{name} bmi_cat"
        # diet allowed + regime must match (fasting safety)
        assert cur["diet"]["allowed"] == exp["diet"]["allowed"], f"{name} diet.allowed"
        assert cur["diet"]["regime"] == exp["diet"]["regime"], f"{name} diet.regime"
        # probable conditions top-3 icd + names
        assert [c["icd10"] for c in cur["probable_conditions"]] == [c["icd10"] for c in exp["probable_conditions"]], f"{name} icds"
        # TASK-004: actions last line changed to qualitative bands (no ~X%).
        # Level guidance lines (all but last) must stay identical to golden.
        assert cur["actions"][:-1] == exp["actions"][:-1], f"{name} actions guidance"
        last = cur["actions"][-1]
        assert "%" not in "".join(cur["actions"]) and "~" not in last, f"{name} honest actions"
        # last line must still reference the same top condition + honest wording
        top_name = exp["probable_conditions"][0]["name"]
        assert top_name in last, f"{name} top condition kept"
        assert any(k in last for k in ("не диагноз", "not a diagnosis", "диагноз емес")), f"{name} honesty marker"
        assert cur["see_doctor"] == exp["see_doctor"], f"{name} see_doctor"
        assert cur["emergency_call"] == exp["emergency_call"], f"{name} emergency"
