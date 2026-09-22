"""Pydantic-модели валидации MediAI."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


Sex = Literal["male", "female", "other"]
TriageLevel = Literal["GREEN", "YELLOW", "ORANGE", "RED"]
SportGoal = Literal["lose", "gain", "maintain", "endurance", "strength"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "athlete"]


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
    symptoms_text: str = Field(..., min_length=3, description="Свободный текст симптомов")
    tags: List[str] = Field(default_factory=list)
    request_diet: bool = False


class TriageQuestion(BaseModel):
    id: str
    text: str
    options: List[str] = Field(default_factory=lambda: ["Да", "Нет", "Не уверен(а)"])
    reason: str = Field(default="", description="Зачем задан вопрос (исключаемое острое состояние)")


class TriageInitialResponse(BaseModel):
    questions: List[TriageQuestion] = Field(..., min_length=3, max_length=3)


class TriageAnswer(BaseModel):
    question_id: str
    answer: str


class TriageFinalRequest(BaseModel):
    age: int = Field(..., ge=0, le=120)
    sex: Sex
    height_cm: float = Field(..., ge=50, le=250)
    weight_kg: float = Field(..., ge=20, le=300)
    body_zone: str = Field(..., min_length=1)
    symptoms_text: str = Field(..., min_length=3)
    tags: List[str] = Field(default_factory=list)
    request_diet: bool = False
    answers: List[TriageAnswer] = Field(..., min_length=3, max_length=3)


class ProbableCondition(BaseModel):
    name: str
    icd10: str
    probability: float = Field(..., ge=0, le=100)
    reason: str = ""


class DietInfo(BaseModel):
    allowed: bool
    regime: str = ""
    reason: str = ""
    recommended: List[str] = Field(default_factory=list)
    forbidden: List[str] = Field(default_factory=list)
    menu_example: List[str] = Field(default_factory=list)
    warning: Optional[str] = None


class EvidenceSource(BaseModel):
    title: str
    url: str
    type: str = Field(description="WHO / PubMed / Protocol")


class TriageFinalResponse(BaseModel):
    bmi: float
    bmi_category: str
    risk_score: float = Field(..., ge=0, le=100)
    triage_level: TriageLevel
    probable_conditions: List[ProbableCondition]
    diet: DietInfo
    actions: List[str]
    see_doctor: str
    emergency_call: bool
    forbidden_actions: List[str]
    evidence_sources: List[EvidenceSource]


class ConditionItem(BaseModel):
    name: str
    icd10: str
    category: str
    urgency_hint: str = ""


class ConditionsResponse(BaseModel):
    categories: Dict[str, List[ConditionItem]]


class SportPlanRequest(BaseModel):
    age: int = Field(..., ge=10, le=100)
    sex: Sex
    height_cm: float = Field(..., ge=120, le=230)
    weight_kg: float = Field(..., ge=30, le=250)
    goal: SportGoal = "lose"
    activity_level: ActivityLevel = "light"
    contraindications: List[str] = Field(default_factory=list)


class SportPlanResponse(BaseModel):
    bmi: float
    bmi_category: str
    bmr_kcal: float
    tdee_kcal: float
    target_kcal: float
    weekly_tempo_kg: str
    timeline_weeks: float
    timeline_text: str
    training_plan: List[str]
    nutrition_hint: List[str]
    contraindications: List[str]
    warnings: List[str]
