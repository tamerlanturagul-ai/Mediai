"""Backward-compat shim: re-export split modules (TASK-003).

New layout:
- app/domain/catalog.py   — RU/EN/KZ catalogs
- app/domain/questions.py — 6 zones x 3 langs banks
- app/domain/rules.py     — normalize, kw scoring, thresholds, surgery
- app/services/triage_service.py — evaluate_final, builders

Old imports ``from app.triage_engine import ...`` keep working.
"""
from __future__ import annotations

from .domain.catalog import (
    CONDITIONS_CATALOG,
    CONDITIONS_CATALOG_EN,
    CONDITIONS_CATALOG_KZ,
    CONDITIONS_CATALOG_RU,
    get_conditions_catalog,
)
from .domain.questions import (
    _OPTIONS_I18N,
    _QUESTION_BANK,
    _QUESTION_BANK_EN,
    _QUESTION_BANK_KZ,
    _QUESTION_BANK_RU,
    _text as _questions_text,
    generate_initial_questions,
)
from .domain.rules import (
    _ABDOMEN_SURGICAL_SIGNALS,
    _BMI_I18N,
    _BMI_SHORT_I18N,
    _GI_BLEED_SIGNALS,
    _RED_PHRASES,
    _answer_is_positive,
    _answer_is_unsure,
    _gi_diabetes_obesity_context,
    _keyword_score,
    _kw_hit,
    _kw_pattern,
    _norm_lang,
    _normalize_med_text,
    _surgery_suspected,
    bmi_category,
    bmi_category_short,
    calc_bmi,
    normalize_answer,
    normalize_zone,
    triage_level_from_score,
)
from .services.triage_service import (
    _build_actions,
    _build_diet,
    _build_evidence,
    _build_probable_conditions,
    _text,
    evaluate_final,
)

__all__ = [
    "CONDITIONS_CATALOG",
    "CONDITIONS_CATALOG_EN",
    "CONDITIONS_CATALOG_KZ",
    "CONDITIONS_CATALOG_RU",
    "get_conditions_catalog",
    "_OPTIONS_I18N",
    "_QUESTION_BANK",
    "_QUESTION_BANK_EN",
    "_QUESTION_BANK_KZ",
    "_QUESTION_BANK_RU",
    "generate_initial_questions",
    "_BMI_I18N",
    "_BMI_SHORT_I18N",
    "_GI_BLEED_SIGNALS",
    "_ABDOMEN_SURGICAL_SIGNALS",
    "_RED_PHRASES",
    "_norm_lang",
    "calc_bmi",
    "bmi_category",
    "bmi_category_short",
    "normalize_zone",
    "triage_level_from_score",
    "normalize_answer",
    "_answer_is_positive",
    "_answer_is_unsure",
    "_normalize_med_text",
    "_kw_pattern",
    "_kw_hit",
    "_keyword_score",
    "_surgery_suspected",
    "_gi_diabetes_obesity_context",
    "evaluate_final",
    "_build_probable_conditions",
    "_build_diet",
    "_build_actions",
    "_build_evidence",
    "_text",
]
