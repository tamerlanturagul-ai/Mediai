"""Backward-compat shim: re-export split modules (TASK-003, deduped TASK-011).

New layout:
- app/i18n.py                  — resolve_lang, normalize_answer, MESSAGES / LIST_MESSAGES
- app/domain/catalog.py        — RU/EN/KZ catalogs
- app/domain/questions.py      — 6 zones x 3 langs banks
- app/domain/rules.py          — normalize, kw scoring, thresholds, surgery
- app/services/triage_service.py — evaluate_final, builders

Old imports ``from app.triage_engine import ...`` keep working for public
names; ``_keyword_score`` stays importable for the committed safety tests.
"""
from __future__ import annotations

from .domain.catalog import (
    CONDITIONS_CATALOG,
    CONDITIONS_CATALOG_EN,
    CONDITIONS_CATALOG_KZ,
    CONDITIONS_CATALOG_RU,
    get_conditions_catalog,
)
from .domain.questions import generate_initial_questions
from .domain.rules import (
    CHRONIC_FLAG,
    CHRONIC_MARKERS,
    CHRONIC_POINTS,
    LIKELIHOOD_I18N,
    RED_SCORE_GROUPS,
    RULES_VERSION,
    _keyword_score,  # noqa: F401  # backward-compat: used by test_triage_safety
    bmi_category,
    bmi_category_short,
    calc_bmi,
    likelihood_band,
    likelihood_label,
    normalize_answer,
    normalize_zone,
    triage_level_from_score,
)
from .i18n import LIST_MESSAGES, MESSAGES, resolve_lang
from .services.triage_service import evaluate_final

__all__ = [
    "CHRONIC_FLAG",
    "CHRONIC_MARKERS",
    "CHRONIC_POINTS",
    "CONDITIONS_CATALOG",
    "CONDITIONS_CATALOG_EN",
    "CONDITIONS_CATALOG_KZ",
    "CONDITIONS_CATALOG_RU",
    "LIKELIHOOD_I18N",
    "LIST_MESSAGES",
    "MESSAGES",
    "RED_SCORE_GROUPS",
    "RULES_VERSION",
    "bmi_category",
    "bmi_category_short",
    "calc_bmi",
    "evaluate_final",
    "generate_initial_questions",
    "get_conditions_catalog",
    "likelihood_band",
    "likelihood_label",
    "normalize_answer",
    "normalize_zone",
    "resolve_lang",
    "triage_level_from_score",
]
