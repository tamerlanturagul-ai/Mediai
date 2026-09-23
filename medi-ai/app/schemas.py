"""Pydantic-модели валидации MediAI."""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from .i18n import normalize_answer as _canonical_normalize_answer
from .i18n import resolve_lang

Sex = Literal["male", "female", "other"]
TriageLevel = Literal["GREEN", "YELLOW", "ORANGE", "RED"]
SportGoal = Literal["lose", "gain", "maintain", "endurance", "strength"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "athlete"]
Lang = Literal["ru", "en", "kz"]
AnswerLiteral = Literal["yes", "no", "unsure"]


def map_localized_answer(v: str) -> str:
    """Map RU/EN/KZ free-text answer to canonical yes/no/unsure.

    Thin delegate of app.i18n.normalize_answer (kept for backward compat).
    Accepted (case-insensitive):
    - yes: да, yes, иә, есть/имеется/наблюдается, бар/болады (+ "да, ..." / "yes, ..." continuations)
    - no: нет, no, жоқ/жок
    - unsure: не уверен(а)/не знаю, not sure, сенімді емес(пін), unsure
    Ambiguous ("да нет") and other free text raise ValueError (contract: Literal only).
    """
    return _canonical_normalize_answer(v)


def map_lang(v: str | None) -> str:
    """Single lang coercion: unknown/empty -> 'ru' (fallback, TASK-003 contract).

    Thin delegate of app.i18n.resolve_lang (kept for backward compat).
    """
    return resolve_lang(v)


class HealthProfile(BaseModel):
    age: int = Field(..., ge=0, le=120, description="Возраст, лет")
    sex: Sex = Field(..., description="Пол")
    height_cm: float = Field(..., ge=50, le=250, description="Рост, см")
    weight_kg: float = Field(..., ge=20, le=300, description="Вес, кг")


class TriageInitialRequest(BaseModel):
    age: int = Field(..., ge=0, le=120)
    sex: Sex
    height_cm: float = Field(..., ge=50, le=250)
    weight_kg: float = Field(..., ge=20, le=300)
    body_zone: str = Field(..., min_length=1, description="Зона тела: chest/abdomen/head/skin/limb и т.д.")
    # TASK-009 P0: bound free text (DoS-sized bodies -> 422, not worker OOM).
    symptoms_text: str = Field(..., min_length=3, max_length=4000, description="Свободный текст симптомов")
    tags: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=20)
    request_diet: bool = False
    lang: Lang = Field(default="ru", description="Язык ответа: ru/en/kz")

    @field_validator("lang", mode="before")
    @classmethod
    def _coerce_lang(cls, v):  # type: ignore[no-untyped-def]
        return map_lang(v if isinstance(v, str) else "ru")


class TriageQuestion(BaseModel):
    id: str
    text: str
    options: list[str] = Field(default_factory=lambda: ["Да", "Нет", "Не уверен(а)"])
    reason: str = Field(default="", description="Зачем задан вопрос (исключаемое острое состояние)")


class TriageInitialResponse(BaseModel):
    questions: list[TriageQuestion] = Field(..., min_length=3, max_length=3)
    lang: Lang = Field(default="ru")


class TriageAnswer(BaseModel):
    question_id: str
    answer: AnswerLiteral

    @field_validator("answer", mode="before")
    @classmethod
    def _coerce_answer(cls, v):  # type: ignore[no-untyped-def]
        if isinstance(v, str):
            return map_localized_answer(v)
        return v


class TriageFinalRequest(BaseModel):
    age: int = Field(..., ge=0, le=120)
    sex: Sex
    height_cm: float = Field(..., ge=50, le=250)
    weight_kg: float = Field(..., ge=20, le=300)
    body_zone: str = Field(..., min_length=1)
    # TASK-009 P0: same bounds as TriageInitialRequest (4000 chars, 20x64 tags).
    symptoms_text: str = Field(..., min_length=3, max_length=4000)
    tags: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=20)
    request_diet: bool = False
    answers: list[TriageAnswer] = Field(..., min_length=3, max_length=3)
    lang: Lang = Field(default="ru")
    # TASK-008: photo envelope for the doctor (B4-variant-1). Ids only —
    # images NEVER influence score/conditions/diet (see evaluate_final).
    photo_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("lang", mode="before")
    @classmethod
    def _coerce_lang(cls, v):  # type: ignore[no-untyped-def]
        return map_lang(v if isinstance(v, str) else "ru")

    @field_validator("photo_ids")
    @classmethod
    def _validate_photo_ids(cls, v):  # type: ignore[no-untyped-def]
        if len(v) > 3:
            raise ValueError("Можно прикрепить не более 3 фото")
        for pid in v:
            try:
                uuid.UUID(str(pid))
            except (ValueError, AttributeError, TypeError):
                raise ValueError(f"Некорректный photo_id '{pid}': ожидается UUID")
        return v


class PhotoAttachment(BaseModel):
    """Photo attached to the triage result FOR THE DOCTOR (not a diagnosis)."""

    photo_id: str
    # TASK-009: "unknown" = stored file became unreadable (never silent "ok").
    quality: Literal["ok", "too_dark", "too_blurry", "unknown"]


class PhotoUploadResponse(BaseModel):
    photo_id: str
    quality: Literal["ok", "too_dark", "too_blurry", "unknown"]
    hint: str = ""


class ProbableCondition(BaseModel):
    name: str
    icd10: str
    probability: float = Field(..., ge=0, le=100)
    reason: str = ""


class DietInfo(BaseModel):
    allowed: bool
    regime: str = ""
    reason: str = ""
    recommended: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    menu_example: list[str] = Field(default_factory=list)
    warning: str | None = None


class EvidenceSource(BaseModel):
    title: str
    url: str
    type: str = Field(description="WHO / PubMed / Protocol")


class ScoreBreakdownItem(BaseModel):
    reason: str
    points: float


class TriageFinalResponse(BaseModel):
    bmi: float
    bmi_category: str
    risk_score: float = Field(..., ge=0, le=100)
    triage_level: TriageLevel
    probable_conditions: list[ProbableCondition]
    diet: DietInfo
    actions: list[str]
    see_doctor: str
    emergency_call: bool
    forbidden_actions: list[str]
    evidence_sources: list[EvidenceSource]
    lang: Lang = Field(default="ru")
    # TASK-004: transparency — how the score was counted + rules version.
    score_breakdown: list[ScoreBreakdownItem] = Field(default_factory=list)
    rules_version: str = Field(default="1.1")
    # TASK-008: photos attached "for the doctor". Carried through only —
    # MUST NOT change score/conditions/diet (asserted in test_photo_upload.py).
    photos_attached: list[PhotoAttachment] = Field(default_factory=list)


class ConditionItem(BaseModel):
    name: str
    icd10: str
    category: str
    urgency_hint: str = ""


class ConditionsResponse(BaseModel):
    categories: dict[str, list[ConditionItem]]


class SportPlanRequest(BaseModel):
    age: int = Field(..., ge=10, le=100)
    sex: Sex
    height_cm: float = Field(..., ge=120, le=230)
    weight_kg: float = Field(..., ge=30, le=250)
    goal: SportGoal = "lose"
    activity_level: ActivityLevel = "light"
    contraindications: list[str] = Field(default_factory=list)
    lang: Lang = Field(default="ru", description="Язык ответа: ru/en/kz")
    # TASK-007: PAR-Q screening (defaults = no positive answers).
    parq_chest_pain: bool = False
    parq_dizziness: bool = False
    parq_joint_problem: bool = False
    parq_heart_condition: bool = False
    parq_diabetes: bool = False
    parq_age50_unsupervised: bool = False
    parq_other: str = Field(default="")

    @field_validator("lang", mode="before")
    @classmethod
    def _coerce_lang(cls, v):  # type: ignore[no-untyped-def]
        return map_lang(v if isinstance(v, str) else "ru")


class SportPlanResponse(BaseModel):
    bmi: float
    bmi_category: str
    bmr_kcal: float
    tdee_kcal: float
    target_kcal: float
    weekly_tempo_kg: str
    timeline_weeks: float
    timeline_text: str
    training_plan: list[str]
    nutrition_hint: list[str]
    contraindications: list[str]
    warnings: list[str]
    lang: Lang = Field(default="ru")
