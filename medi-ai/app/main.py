"""Сервер FastAPI MediAI: роуты, статика, CORS."""
# NOTE (TASK-009): no `from __future__ import annotations` here on purpose.
# slowapi's @limiter.limit wraps endpoints, and FastAPI resolves parameter
# annotations in the wrapper's module namespace when they are PEP 563
# strings (UploadFile then fails as ForwardRef). Real annotations avoid that.

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from .domain.rules import RULES_VERSION
from .i18n import resolve_lang
from .schemas import (
    ConditionsResponse,
    PhotoAttachment,
    PhotoUploadResponse,
    SportPlanRequest,
    SportPlanResponse,
    TriageFinalRequest,
    TriageFinalResponse,
    TriageInitialRequest,
    TriageInitialResponse,
)
from .security import (
    LIMIT_CONDITIONS,
    LIMIT_PHOTO_DELETE,
    LIMIT_PHOTO_GET,
    LIMIT_SPORT_PLAN,
    LIMIT_TRIAGE_FINAL,
    LIMIT_TRIAGE_INITIAL,
    LIMIT_TRIAGE_PHOTO,
    get_api_keys,
    key_matches,
    limiter,
    requires_auth,
    set_security_headers,
)
from .services.photo_service import (
    EXT_TO_MEDIA_TYPE,
    MAX_PHOTO_BYTES,
    MAX_PHOTOS_PER_TRIAGE,
    PhotoUploadError,
    delete_photo,
    get_photo_info,
    get_photo_path,
    photo_exists,
    save_photo,
    sweep_expired_photos,
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

# TASK-012 release: single app version const (mirrors FastAPI version + pyproject).
APP_VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# TASK-009 P0: generic client-facing error texts. Full tracebacks / paths /
# module names / str(exc) go to server logs only, never to the client.
GENERIC_VALIDATION_ERROR = "Ошибка валидации запроса. Проверьте параметры и попробуйте снова."
GENERIC_SERVER_ERROR = "Внутренняя ошибка сервера."
GENERIC_RATE_LIMIT_ERROR = "Превышен лимит запросов. Попробуйте позже."
GENERIC_AUTH_ERROR = "Нужен API-ключ (заголовок X-API-Key)."

# Multipart framing overhead slack for the early Content-Length pre-check.
# The exact 8 MB cap is enforced on file bytes during the chunked read.
UPLOAD_EARLY_REJECT_SLACK = 64 * 1024
UPLOAD_READ_CHUNK = 1024 * 1024  # 1 MB


def _cors_origins() -> list[str]:
    """Whitelist from CORS_ORIGINS env (comma-separated). No '*' default."""
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw.strip():
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _resolve_lang(lang: str | None) -> str:
    """Single lang helper for all triage routes: fallback to 'ru'.

    Thin delegate of app.i18n.resolve_lang (kept for backward compat).
    Contract (documented in README): unknown/empty lang -> 'ru'
    (no 422, backward-compatible). Used identically in
    /api/conditions, /api/triage/initial, /api/triage/final.
    """
    return resolve_lang(lang)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """TASK-012: TTL sweep on startup (best effort, never blocks boot)."""
    try:
        sweep_expired_photos()
    except Exception:
        logger.exception("photo TTL sweep failed on startup")
    yield


app = FastAPI(title="MediAI — первичный клинический триаж", version=APP_VERSION, lifespan=lifespan)

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

# TASK-009 P0: rate limiter state + 429 handler (generic body, no internals).
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    resp = JSONResponse(status_code=429, content={"detail": GENERIC_RATE_LIMIT_ERROR})
    return set_security_headers(resp)


@app.exception_handler(RequestValidationError)
def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # TASK-009 P0: 422 with GENERIC text. Field names / rejected values /
    # paths stay in server logs only.
    logger.warning("validation failed: %s %s", request.method, request.url.path)
    resp = JSONResponse(status_code=422, content={"detail": GENERIC_VALIDATION_ERROR})
    return set_security_headers(resp)


@app.exception_handler(Exception)
def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    # TASK-009 P0: unexpected failure -> logged with traceback, client gets
    # a generic 500. (HTTPException keeps its own handler: Starlette matches
    # HTTPException before this generic Exception handler in the MRO walk.)
    logger.exception("unhandled error: %s %s", request.method, request.url.path)
    resp = JSONResponse(status_code=500, content={"detail": GENERIC_SERVER_ERROR})
    return set_security_headers(resp)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next: object) -> Response:
    """TASK-009 P0: X-API-Key gate on all /api/* except /api/health.

    Keys come from the API_KEYS env var (comma-separated). When API_KEYS is
    unset/empty the API stays open (local dev + legacy tests); production
    MUST set API_KEYS. Comparison is constant-time (hmac.compare_digest).
    """
    if requires_auth(request.url.path, request.method):
        keys = get_api_keys()
        if keys and not key_matches(request.headers.get("x-api-key"), keys):
            return set_security_headers(JSONResponse(status_code=401, content={"detail": GENERIC_AUTH_ERROR}))
    resp = await call_next(request)  # type: ignore[operator]
    return set_security_headers(resp)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: object) -> Response:
    """TASK-012: hardening headers on every response (idempotent)."""
    resp = await call_next(request)  # type: ignore[operator]
    return set_security_headers(resp)


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="static/index.html не найден")
    return FileResponse(str(INDEX_HTML), media_type="text/html")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe (always open) + release versions for ops pinning."""
    return {"status": "ok", "service": "medi-ai", "version": APP_VERSION, "rules_version": RULES_VERSION}


@app.get("/api/conditions", response_model=ConditionsResponse)
@limiter.limit(LIMIT_CONDITIONS)
def list_conditions(request: Request, lang: str = "ru") -> ConditionsResponse:
    lang = _resolve_lang(lang)
    catalog = get_conditions_catalog(lang)
    return ConditionsResponse(categories=catalog)


@app.post("/api/triage/initial", response_model=TriageInitialResponse)
@limiter.limit(LIMIT_TRIAGE_INITIAL)
def triage_initial(request: Request, req: TriageInitialRequest) -> TriageInitialResponse:
    questions = generate_initial_questions(req)
    # Гарантия контракта: ровно 3 вопроса
    if len(questions) != 3:
        raise HTTPException(status_code=500, detail="Движок вернул не 3 вопроса")
    lang = _resolve_lang(getattr(req, "lang", "ru"))
    return TriageInitialResponse(questions=questions, lang=lang)  # type: ignore[arg-type]  # lang narrowed to ru/en/kz by _resolve_lang contract


def _read_upload_capped(file: UploadFile) -> bytes:
    """Chunked file read with an exact MAX_PHOTO_BYTES cap -> 413.

    Runs in a worker thread (sync endpoint): no event-loop blocking, no
    unbounded buffering of attacker-controlled bodies.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(UPLOAD_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_PHOTO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой (максимум {MAX_PHOTO_BYTES} байт).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/triage/photo", response_model=PhotoUploadResponse)
@limiter.limit(LIMIT_TRIAGE_PHOTO)
def triage_photo(request: Request, file: UploadFile = File(...)) -> PhotoUploadResponse:  # noqa: B008  # FastAPI idiom: File(...) is a marker consumed by FastAPI, never called at runtime
    """Store a photo envelope for the doctor (TASK-008, B4-variant-1).

    Accepts jpeg/png/webp up to 8 MB. Returns {photo_id, quality, hint}.
    The image is NEVER a diagnostic signal: quality is a Pillow-only
    capture hint (ok | too_dark | too_blurry), no ML, no diagnosis.

    TASK-009 P0: sync def (FastAPI threadpool, no event-loop blocking on
    Pillow); early Content-Length pre-check + chunked capped read -> 413.
    """
    raw_len = request.headers.get("content-length")
    if raw_len is not None:
        try:
            if int(raw_len) > MAX_PHOTO_BYTES + UPLOAD_EARLY_REJECT_SLACK:
                raise HTTPException(
                    status_code=413,
                    detail=f"Файл слишком большой (максимум {MAX_PHOTO_BYTES} байт).",
                )
        except ValueError:
            pass
    data = _read_upload_capped(file)
    try:
        saved = save_photo(data, file.content_type, file.filename)
    except PhotoUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return PhotoUploadResponse(**saved)


@app.get("/api/triage/photo/{photo_id}")
@limiter.limit(LIMIT_PHOTO_GET)
def get_photo(request: Request, photo_id: str) -> FileResponse:
    """TASK-012: retrieve a stored photo (auth-gated like other /api/*).

    The api_key_middleware already enforces X-API-Key when API_KEYS is set;
    /api/health stays the only open probe. Unknown/invalid ids -> 404
    (generic body, no path leaks).
    """
    path = get_photo_path(photo_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    media_type = EXT_TO_MEDIA_TYPE.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type)


@app.delete("/api/triage/photo/{photo_id}")
@limiter.limit(LIMIT_PHOTO_DELETE)
def remove_photo(request: Request, photo_id: str) -> dict[str, object]:
    """TASK-012: delete a photo envelope.

    Ownership: holder of a valid X-API-Key (enforced by middleware when
    API_KEYS is set). When auth is disabled (local dev, no API_KEYS) any
    client may delete — production MUST set API_KEYS (see README).
    Unknown ids -> 404.
    """
    if not delete_photo(photo_id):
        raise HTTPException(status_code=404, detail="Фото не найдено")
    return {"deleted": True, "photo_id": photo_id}


@app.post("/api/triage/final", response_model=TriageFinalResponse)
@limiter.limit(LIMIT_TRIAGE_FINAL)
def triage_final(request: Request, req: TriageFinalRequest) -> TriageFinalResponse:
    # TASK-008: photo_ids are validated here (UUID format + max 3 already
    # enforced by schema). Unknown ids -> 422. Attached photos are carried
    # into the response "for the doctor" and MUST NOT change the score —
    # evaluate_final never sees photo_ids.
    if len(req.photo_ids) > MAX_PHOTOS_PER_TRIAGE:
        raise HTTPException(status_code=422, detail="Можно прикрепить не более 3 фото")
    attached: list[PhotoAttachment] = []
    for pid in req.photo_ids:
        info = get_photo_info(pid)
        if info is None and not photo_exists(pid):
            raise HTTPException(status_code=422, detail=f"Неизвестный photo_id '{pid}'")
        info = info or {"photo_id": pid, "quality": "unknown"}
        attached.append(PhotoAttachment(photo_id=info["photo_id"], quality=info["quality"]))  # type: ignore[arg-type]
    try:
        result = evaluate_final(req)
    except ValueError:
        # TASK-009 P0: validation-flavoured engine failure -> generic 422.
        logger.warning("triage evaluation rejected: %s %s", request.method, request.url.path)
        raise HTTPException(status_code=422, detail=GENERIC_VALIDATION_ERROR)
    except Exception:
        # TASK-009 P0: unexpected failure -> logged, generic 500 (no str(exc)).
        logger.exception("triage evaluation failed: %s %s", request.method, request.url.path)
        raise HTTPException(status_code=500, detail=GENERIC_SERVER_ERROR)
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
        score_breakdown=result.get("score_breakdown", []),
        rules_version=result.get("rules_version", "1.1"),
        photos_attached=attached,
    )


@app.post("/api/sport/plan", response_model=SportPlanResponse)
@limiter.limit(LIMIT_SPORT_PLAN)
def sport_plan(request: Request, req: SportPlanRequest) -> SportPlanResponse:
    try:
        result = build_sport_plan(req)
    except ValueError:
        # TASK-009 P0: validation-flavoured engine failure -> generic 422.
        logger.warning("sport plan rejected: %s %s", request.method, request.url.path)
        raise HTTPException(status_code=422, detail=GENERIC_VALIDATION_ERROR)
    except Exception:
        # TASK-009 P0: unexpected failure -> logged, generic 500 (no str(exc)).
        logger.exception("sport plan failed: %s %s", request.method, request.url.path)
        raise HTTPException(status_code=500, detail=GENERIC_SERVER_ERROR)
    return SportPlanResponse(**result)


@app.exception_handler(404)
def not_found_handler(request: Request, exc: HTTPException) -> Response:
    if str(request.url.path).startswith("/api/"):
        return set_security_headers(JSONResponse(status_code=404, content={"detail": "Эндпоинт не найден"}))
    # Для SPA-маршрутов отдаём index.html, если он есть
    if INDEX_HTML.exists():
        return set_security_headers(FileResponse(str(INDEX_HTML), media_type="text/html"))
    return set_security_headers(JSONResponse(status_code=404, content={"detail": "Не найдено"}))


if __name__ == "__main__":
    import uvicorn

    # TASK-012 prod: loopback only, no reload (Dockerfile runs uvicorn --workers).
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
