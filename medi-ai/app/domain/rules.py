"""Domain rules: language, zones, BMI, keyword scoring, surgery/diet contexts.

Extracted 1:1 from app/triage_engine.py (TASK-003 split).
Intentional contract changes vs TASK-002 baseline:
- normalize_zone: throat/горло (+шея, already) -> head (was general).
- _kw_pattern default: prefix-tolerant ``\\b<kw>\\w*\\b`` (was exact
  ``\\b<kw>\\b``) to keep inflection sensitivity (грудиной, диабетом,
  подвздошная, migrating) while preserving word-start safety
  (breakfast != FAST, 139/9 != 39). Special cases (39, 38.5,
  температура 39/40, fast) stay exact.
- Answer mapping: normalize_answer() maps RU/EN/KZ free text to
  canonical yes/no/unsure (see schemas.TriageAnswer).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..i18n import normalize_answer as _canonical_normalize_answer
from ..i18n import resolve_lang

if TYPE_CHECKING:  # schemas import is typing-only: keeps domain runtime-decoupled
    from ..schemas import ProbableCondition

# TASK-004: honest outputs — rules version exposed to client via score_breakdown.
RULES_VERSION = "1.1"


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

def _norm_lang(lang: str | None) -> str:
    """Deprecated alias of app.i18n.resolve_lang (kept for backward compat)."""
    return resolve_lang(lang)


# ---------------------------------------------------------------------------
# BMI
# ---------------------------------------------------------------------------

def calc_bmi(weight_kg: float, height_cm: float) -> float:
    h_m = max(height_cm / 100.0, 0.5)
    return round(weight_kg / (h_m ** 2), 1)


_BMI_I18N = {
    "ru": ["Дефицит массы тела", "Норма", "Избыточная масса тела",
           "Ожирение I степени", "Ожирение II степени", "Ожирение III степени"],
    "en": ["Underweight", "Normal", "Overweight",
           "Obesity class I", "Obesity class II", "Obesity class III"],
    "kz": ["Салмақ тапшылығы", "Қалыпты", "Артық салмақ",
           "I дәрежелі семіздік", "II дәрежелі семіздік", "III дәрежелі семіздік"],
}

_BMI_SHORT_I18N = {
    "ru": ["Дефицит", "Норма", "Избыток", "Ожирение"],
    "en": ["Low", "Normal", "High", "Obese"],
    "kz": ["Тапшылық", "Қалыпты", "Артық", "Семіздік"],
}


def bmi_category(bmi: float, lang: str = "ru") -> str:
    lang = resolve_lang(lang)
    full = _BMI_I18N[lang]
    if bmi < 18.5:
        return full[0]
    if bmi < 25:
        return full[1]
    if bmi < 30:
        return full[2]
    if bmi < 35:
        return full[3]
    if bmi < 40:
        return full[4]
    return full[5]


def bmi_category_short(bmi: float, lang: str = "ru") -> str:
    lang = resolve_lang(lang)
    s = _BMI_SHORT_I18N[lang]
    if bmi < 18.5:
        return s[0]
    if bmi < 25:
        return s[1]
    if bmi < 30:
        return s[2]
    return s[3]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

# Zone keyword table: (zone, substring keys), checked in order; fallback "general".
_ZONE_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chest", ("chest", "груд", "сердц", "thorax", "кардио")),
    ("abdomen", ("abdomen", "живот", "абдомин", "брюш", "подвздош", "эпигастр", "жкт", "кишеч", "желуд")),
    # TASK-003 contract: throat/горло/шея -> head (no dedicated throat zone).
    ("head", ("head", "голов", "невро", "мозг", "шея", "neuro", "мигрень",
              "throat", "горло", "горл", "тамак", "тамақ")),
    ("skin", ("skin", "кожа", "дерм", "сыпь", "прыщ", "зуд", "дермат")),
    ("limb", ("limb", "нога", "рука", "конечн", "спина", "поясниц", "сустав", "колен")),
)


def normalize_zone(body_zone: str) -> str:
    z = (body_zone or "").strip().lower()
    for zone, keys in _ZONE_TABLE:
        if any(key in z for key in keys):
            return zone
    return "general"


def triage_level_from_score(score: float) -> str:
    if score <= 25:
        return "GREEN"
    if score <= 60:
        return "YELLOW"
    if score <= 85:
        return "ORANGE"
    return "RED"


# ---------------------------------------------------------------------------
# Answers: RU/EN/KZ -> canonical yes/no/unsure
# ---------------------------------------------------------------------------

def normalize_answer(answer: str) -> str:
    """Map localized answer text to canonical 'yes' | 'no' | 'unsure'.

    Thin delegate of app.i18n.normalize_answer (kept here for backward compat).
    Raises ValueError for unmapped/ambiguous free text (contract: Literal only).
    """
    return _canonical_normalize_answer(answer)


def _answer_is_positive(answer: str) -> bool:
    # Canonical fast path + legacy fallback (1:1 with pre-split logic).
    try:
        return normalize_answer(answer) == "yes"
    except ValueError:
        pass
    a = (answer or "").strip().lower()
    if a in ("да", "yes", "есть", "имеется", "наблюдается", "иә", "бар", "болады"):
        return True
    return a.startswith(("да", "yes", "иә"))


def _answer_is_unsure(answer: str) -> bool:
    try:
        return normalize_answer(answer) == "unsure"
    except ValueError:
        pass
    a = (answer or "").lower()
    return any(k in a for k in ["не уверен", "не знаю", "not sure", "сенімді емес"])


_RED_PHRASES = ["да", "yes", "есть", "сильная", "резко", "внезапно", "не могу", "невозможно"]


# ---------------------------------------------------------------------------
# Keyword scoring (word-boundary, Unicode-aware)
# ---------------------------------------------------------------------------

def _normalize_med_text(s: str) -> str:
    """Normalized lowercase text for word-boundary matching (Unicode-aware)."""
    return (s or "").lower().replace("ё", "е")


def _kw_pattern(kw: str) -> str:
    k = _normalize_med_text(kw)
    if k == "39":
        return r"\b39\b"
    if k == "38.5":
        return r"\b38[.,]5\b"
    if k == "температура 39":
        return r"\bтемпература\s*:?\s*39\b"
    if k == "температура 40":
        return r"\bтемпература\s*:?\s*40\b"
    if k == "fast":
        return r"\bfast\b"
    if k == "faint":
        # keep sensitivity to faint/fainting/faainted with word-start boundary
        return r"\bfaint\w*\b"
    if k == "fever":
        return r"\bfever\w*\b"
    if k == "анафилакси":
        # stem of анафилаксия/анафилактический — allow suffix, require word start
        return r"\bанафилакси\w*\b"
    # TASK-003: prefix-tolerant for inflections (грудиной, диабетом,
    # подвздошная, migrating) with word-start safety (breakfast != fast).
    return r"\b" + re.escape(k) + r"\w*\b"


def _kw_hit(kw: str, text_norm: str) -> bool:
    try:
        return re.search(_kw_pattern(kw), text_norm, flags=re.UNICODE) is not None
    except re.error:
        return _normalize_med_text(kw) in text_norm


def _keyword_score(t: str) -> tuple[float, list[str]]:
    """Эвристический скоринг по свободному тексту. Возвращает (баллы, флаги)."""
    score, flags, _ = _keyword_score_detailed(t)
    return score, flags


# TASK-004: single source of truth for keyword weights (no retune).
# (keywords, points, flag) — identical values to pre-004 _keyword_score.
RED_SCORE_GROUPS: list[tuple[list[str], float, str]] = [
    (["боль за грудиной", "давит в груди", "жжет в груди", "отдаёт в руку", "холодный пот", "удушье", "нехватка воздуха",
      "chest pain", "pressing chest", "cold sweat", "shortness of breath", "төс артындағы ауырсыну", "суық тер", "ентігу"], 38, "кардиальный красный флаг"),
    (["перекос лица", "онемела рука", "нарушение речи", "инсульт", "fast", "face droop", "arm weakness", "stroke", "бет қисаюы"], 42, "неврологический красный флаг (FAST)"),
    (["рвота кофейной", "черный стул", "мелена", "кровь в стуле", "кровотечение", "coffee-ground", "black stool", "bleeding", "қара нәжіс"], 40, "кровотечение ЖКТ"),
    (["острая боль справа внизу", "миграция боли", "твёрдый живот", "твердый живот", "доскообразный", "нет стула и газов", "задержка стула",
      "right lower", "migrating pain", "rigid abdomen", "оң жақ", "қатайған іш"], 36, "острая хирургическая патология"),
    (["анафилакси", "отёк губ", "отек губ", "отёк языка", "задыхаюсь", "anaphylaxis", "lip swelling", "анафилаксия"], 45, "анафилаксия"),
    (["температура 39", "температура 40", "38.5", "39", "озноб", "спутанность", "потеря сознания", "обморок", "судороги",
      "fever", "chills", "confusion", "faint", "қызба", "қалтырау"], 25, "системная тяжесть"),
    (["тошнота", "рвота", "лихорадка", "температура", "nausea", "vomiting", "жүрек айну", "құсу"], 10, "системные симптомы"),
]

CHRONIC_MARKERS = ["диабет", "давление", "гипертония", "астма", "ибс", "инфаркт в прошлом", "diabetes", "hypertension", "asthma", "қант диабеті"]
CHRONIC_POINTS = 6.0
CHRONIC_FLAG = "отягощённый анамнез"


def _keyword_score_detailed(t: str) -> tuple[float, list[str], list[dict[str, float | str]]]:
    """Same weights as _keyword_score + per-reason points for transparency.

    Returns (total, flags, breakdown) where breakdown is a list of
    {"reason": flag, "points": pts} in hit order. No new weights.
    """
    score = 0.0
    flags: list[str] = []
    breakdown: list[dict[str, float | str]] = []
    tn = _normalize_med_text(t)
    for keywords, pts, flag in RED_SCORE_GROUPS:
        if any(_kw_hit(k, tn) for k in keywords):
            score += pts
            flags.append(flag)
            breakdown.append({"reason": flag, "points": float(pts)})
    # Возраст и хронические маркеры
    if any(_kw_hit(k, tn) for k in CHRONIC_MARKERS):
        score += CHRONIC_POINTS
        flags.append(CHRONIC_FLAG)
        breakdown.append({"reason": CHRONIC_FLAG, "points": float(CHRONIC_POINTS)})
    return score, flags, breakdown


# ---------------------------------------------------------------------------
# TASK-004: qualitative likelihood bands (documented thresholds).
# prob < 30 -> low; 30 <= prob <= 60 -> medium; prob > 60 -> high.
# Numeric probability stays in JSON for compat; human text uses bands only.
# ---------------------------------------------------------------------------

LIKELIHOOD_I18N: dict[str, dict[str, str]] = {
    "ru": {"low": "низкая", "medium": "средняя", "high": "высокая"},
    "en": {"low": "low", "medium": "medium", "high": "high"},
    "kz": {"low": "төмен", "medium": "орташа", "high": "жоғары"},
}


def likelihood_band(probability: float) -> str:
    """Map numeric probability to qualitative band: low / medium / high."""
    p = float(probability)
    if p < 30:
        return "low"
    if p <= 60:
        return "medium"
    return "high"


def likelihood_label(probability: float, lang: str = "ru") -> str:
    """Localized band label (ru/en/kz), fallback to ru."""
    lang = resolve_lang(lang)
    return LIKELIHOOD_I18N[lang][likelihood_band(probability)]


# ---------------------------------------------------------------------------
# Surgery / GI contexts (migrated to _kw_hit, TASK-003)
# ---------------------------------------------------------------------------

_GI_BLEED_SIGNALS = [
    "мелена", "черный стул", "рвота кофейной", "кровотечение",
    "bleeding", "black stool", "coffee-ground", "қара нәжіс",
    "кровь в стуле",
]

_ABDOMEN_SURGICAL_SIGNALS = [
    "аппендицит", "справа внизу", "подвздош", "твёрдый живот",
    "твердый живот", "нет стула", "непроходимость", "доскообразный",
]


def _surgery_suspected(zone: str, t: str, probable: list[ProbableCondition]) -> bool:
    tn = _normalize_med_text(t)
    if zone == "abdomen" and any(_kw_hit(k, tn) for k in _ABDOMEN_SURGICAL_SIGNALS):
        return True
    icds = " ".join(p.icd10 for p in probable)
    if "K35" in icds or "K56" in icds:
        return True
    # GI-bleed in ANY zone → strict fasting (zone-independent).
    return any(_kw_hit(k, tn) for k in _GI_BLEED_SIGNALS)


def _gi_diabetes_obesity_context(t: str, probable: list[ProbableCondition], bmi: float) -> bool:
    tn = _normalize_med_text(t)
    icds = " ".join(p.icd10 for p in probable)
    gi_markers = ["K21", "K25", "K29", "K59", "E11", "E66", "K80"]
    if any(m in icds for m in gi_markers):
        return True
    if bmi >= 30:
        return True
    # TASK-003: migrated from `k in t` substring to _kw_hit.
    return any(_kw_hit(k, tn) for k in ["изжога", "гастрит", "язва", "диабет", "жажда", "ожирение", "понос", "запор", "вздутие"])
