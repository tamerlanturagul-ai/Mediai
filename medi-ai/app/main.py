"""Сервер FastAPI MediAI: роуты, статика, CORS."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .schemas import (
    ConditionsResponse,
    SportPlanRequest,
    SportPlanResponse,
    TriageFinalRequest,
    TriageFinalResponse,
    TriageInitialRequest,
    TriageInitialResponse,
)
from .sport_engine import build_sport_plan
from .triage_engine import (
    evaluate_final,
    generate_initial_questions,
    get_conditions_catalog,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def _cors_origins() -> list[str]:
    """Whitelist from CORS_ORIGINS env (comma-separated). No '*' default."""
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw.strip():
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _resolve_lang(lang: str | None) -> str:
    """Single lang helper for all triage routes: fallback to 'ru'.

    Contract (documented in README): unknown/empty lang -> 'ru'
    (no 422, backward-compatible). Used identically in
    /api/conditions, /api/triage/initial, /api/triage/final.
    """
    l = (lang or "ru").lower()
    return l if l in ("ru", "en", "kz") else "ru"


app = FastAPI(title="MediAI — первичный клинический триаж", version="1.0.0")

# CORS: whitelist only; never '*' + credentials (browsers reject it).
_CORS_ORIGINS = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=("*" not in _CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="static/index.html не найден")
    return FileResponse(str(INDEX_HTML), media_type="text/html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "medi-ai"}


@app.get("/api/conditions", response_model=ConditionsResponse)
def list_conditions(lang: str = "ru") -> ConditionsResponse:
    lang = _resolve_lang(lang)
    catalog = get_conditions_catalog(lang)
    return ConditionsResponse(categories=catalog)


@app.post("/api/triage/initial", response_model=TriageInitialResponse)
def triage_initial(req: TriageInitialRequest) -> TriageInitialResponse:
    questions = generate_initial_questions(req)
    # Гарантия контракта: ровно 3 вопроса
    if len(questions) != 3:
        raise HTTPException(status_code=500, detail="Движок вернул не 3 вопроса")
    lang = _resolve_lang(getattr(req, "lang", "ru"))
    return TriageInitialResponse(questions=questions, lang=lang)  # type: ignore[arg-type]


@app.post("/api/triage/final", response_model=TriageFinalResponse)
def triage_final(req: TriageFinalRequest) -> TriageFinalResponse:
    try:
        result = evaluate_final(req)
    except Exception as exc:  # fail-safe с понятным сообщением
        raise HTTPException(status_code=422, detail=f"Ошибка оценки триажа: {exc}") from exc
    lang = _resolve_lang(getattr(req, "lang", "ru"))
    return TriageFinalResponse(
        bmi=result["bmi"],
        bmi_category=result["bmi_category"],
        risk_score=result["risk_score"],
        triage_level=result["triage_level"],
        probable_conditions=result["probable_conditions"],
        diet=result["diet"],
        actions=result["actions"],
        see_doctor=result["see_doctor"],
        emergency_call=result["emergency_call"],
        forbidden_actions=result["forbidden_actions"],
        evidence_sources=result["evidence_sources"],
        lang=lang,  # type: ignore[arg-type]
    )


@app.post("/api/sport/plan", response_model=SportPlanResponse)
def sport_plan(req: SportPlanRequest) -> SportPlanResponse:
    try:
        result = build_sport_plan(req)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ошибка расчёта спорт-плана: {exc}") from exc
    return SportPlanResponse(**result)


@app.exception_handler(404)
def not_found_handler(request, exc):  # type: ignore[no-untyped-def]
    if str(request.url.path).startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Эндпоинт не найден"})
    # Для SPA-маршрутов отдаём index.html, если он есть
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML), media_type="text/html")
    return JSONResponse(status_code=404, content={"detail": "Не найдено"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
