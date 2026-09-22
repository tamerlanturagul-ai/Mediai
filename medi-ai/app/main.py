"""Сервер FastAPI MediAI: роуты, статика, CORS."""
from __future__ import annotations

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

app = FastAPI(title="MediAI — первичный клинический триаж", version="1.0.0")

# CORS для бесперебойной работы фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
def list_conditions() -> ConditionsResponse:
    catalog = get_conditions_catalog()
    return ConditionsResponse(categories=catalog)


@app.post("/api/triage/initial", response_model=TriageInitialResponse)
def triage_initial(req: TriageInitialRequest) -> TriageInitialResponse:
    questions = generate_initial_questions(req)
    # Гарантия контракта: ровно 3 вопроса
    if len(questions) != 3:
        raise HTTPException(status_code=500, detail="Движок вернул не 3 вопроса")
    return TriageInitialResponse(questions=questions)


@app.post("/api/triage/final", response_model=TriageFinalResponse)
def triage_final(req: TriageFinalRequest) -> TriageFinalResponse:
    try:
        result = evaluate_final(req)
    except Exception as exc:  # fail-safe с понятным сообщением
        raise HTTPException(status_code=422, detail=f"Ошибка оценки триажа: {exc}") from exc
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
