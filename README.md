# MediAI — интеллектуальная платформа первичного клинического триажа

MediAI анализирует симптомы своими словами, зону тела и профиль пользователя (возраст, пол, рост, вес),
проводит первичный скрининг через 3 уточняющих вопроса для исключения острых состояний,
оценивает риски по шкале срочности, возвращает вероятные диагнозы с кодами МКБ-10,
лечебное питание, пошаговый план действий и ссылки на доказательную медицину.
Отдельный модуль рассчитывает безопасный спортивный план с реалистичными сроками.

Стек: Python (FastAPI + Uvicorn + Pydantic) + статический фронтенд (HTML/JS/Tailwind CSS).
UI — CLINICAL CONSOLE (TASK-024, спек — `medi-ai/DESIGN.md`): hero + 3-pill step rail + сетка интейк/консультация (5fr/7fr при ≥1120px).
Токены на CSS-переменных (~50: surfaces/ink/lines, teal-акцент, семантика `data-level`/`data-kind`); закрыт дефект A2 — YELLOW-бейдж `#713f12` на `#facc15` (контраст ~6:1).
Ответы хранятся и шлются каноном `yes`/`no`/`unsure` независимо от языка UI (RU/EN/KZ); шрифт Golos Text вендорен (офлайн, OFL-1.1).

## Запуск для жюри (30 секунд)

Дабл-клик `start-jury.bat` (корень репозитория) → откроется `http://127.0.0.1:8001`.
Демо-путь: пресет «Давящая боль в груди» → «Отправить» → ответить на 3 вопроса → галочка согласия → «Получить оценку риска».
Требуется только Python 3.10+; после установки зависимостей интернет не нужен (фронт и шрифты вендорены, без CDN).
Порт 8001 выбран, чтобы не конфликтовать с классическим `:8000`.

## Структура проекта

```text
medi-ai/
├── DESIGN.md              # TASK-024: спек нового UI CLINICAL CONSOLE
├── Dockerfile             # TASK-012: python:3.12-slim, non-root, uvicorn --workers 2, no reload
├── .dockerignore          # TASK-012: uploads/tests/__pycache__/.git вне образа
├── app/
│   ├── main.py              # FastAPI-сервер, роуты, CORS, статика (+ photo GET/DELETE, headers, health v)
│   ├── schemas.py           # Pydantic-модели валидации
│   ├── security.py          # API_KEYS auth + slowapi rate limits (TASK-009) + headers (TASK-012)
│   ├── triage_engine.py     # Shim ре-экспорта (TASK-003); логика в domain//services
│   ├── domain/
│   │   ├── catalog.py       # RU/EN/KZ каталоги заболеваний
│   │   ├── questions.py     # Банки 6 зон × 3 языка
│   │   └── rules.py         # _normalize_med_text, _kw_pattern/_kw_hit/_keyword_score, _surgery_suspected, пороги
│   ├── services/
│   │   ├── triage_service.py# evaluate_final, builders
│   │   └── photo_service.py # хранение фото + Pillow-оценка качества (TASK-008) + EXIF/TTL/sidecar (TASK-012)
│   ├── sport_engine.py      # Расчёт спорта: темп, сроки, противопоказания, PAR-Q
│   ├── uploads/             # загруженные фото (git-ignored, никогда не коммитить)
│   └── static/
│       ├── index.html       # Главная страница (XSS-safe DOM, без CDN; TASK-024: реворк CLINICAL CONSOLE, 1614 строк)
│       ├── fonts/*.woff2    # TASK-024: вендоренный Golos Text 400/500/600 × cyrillic/latin (OFL-1.1, офлайн)
│       ├── mark.png         # TASK-024: знак 256×256 (transparent)
│       ├── favicon.png      # TASK-024: фавикон 64×64
│       └── tailwind.css     # TASK-012: вендоренный pinned CSS (Tailwind v3.4 значения, офлайн)
├── tests/
│   ├── conftest.py          # fixtures: client, tmp_upload_dir (TASK-010)
│   └── test_*.py            # 10 модулей: contracts, golden_regression, honest_outputs, i18n_dedup, p0_security, photo_upload, release, sport_hardening, tone_presets_stages, triage_safety
└── requirements.txt     # fastapi, uvicorn, pydantic, httpx, pillow, python-multipart, slowapi
```

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/` | Главная страница `app/static/index.html` |
| `GET` | `/api/health` | Проверка состояния: `{status, service, version, rules_version}` (TASK-012: `version` = `APP_VERSION`, `rules_version` = `RULES_VERSION`) |
| `GET` | `/api/conditions` | Каталог заболеваний для мега-меню: кардиология, гастроэнтерология, неврология, дерматология, хирургия (с кодами МКБ-10) |
| `POST` | `/api/triage/initial` | Первичный скрининг. Принимает профиль, зону тела, текст симптомов, теги и флаг запроса диеты. Возвращает ровно 3 уточняющих вопроса |
| `POST` | `/api/triage/final` | Финальная оценка. Возвращает ИМТ, `triage_level` (GREEN 0–25% / YELLOW 26–60% / ORANGE 61–85% / RED 86–100%), `probable_conditions` с МКБ-10, `diet`, `actions`, `evidence_sources` |
| `POST` | `/api/sport/plan` | Безопасный темп трансформации тела, физиологичные сроки, противопоказания (запрет ударного бега при ИМТ > 30) |
| `POST` | `/api/triage/photo` | Фото-конверт для врача (TASK-008, B4-variant-1). Multipart `file`: jpeg/png/webp до 8 МБ, лимит 40 Мпикс. Возвращает `{photo_id, quality, hint}`, где `quality` — только подсказка качества съёмки (`ok` \| `too_dark` \| `too_blurry` \| `unknown`, Pillow-эвристики, без ML и без диагноза). Фото НИКОГДА не влияет на скоринг |
| `GET` | `/api/triage/photo/{id}` | TASK-012: выдача фото по `photo_id` (UUID). Auth-gated как остальные `/api/*` (401 без ключа, когда задан `API_KEYS`). Неизвестный id → 404 |
| `DELETE` | `/api/triage/photo/{id}` | TASK-012: удаление фото-конверта. Владелец = держатель валидного `X-API-Key` (когда `API_KEYS` задан; без `API_KEYS` — dev-режим, удалить может любой; production ОБЯЗАН задать ключи). Неизвестный id → 404 |

Фото-конверт: `photo_id` (UUID) из `/api/triage/photo` передаётся в `photo_ids` (`POST /api/triage/final`, максимум 3 шт.).
Неизвестный `photo_id` → 422. Прикреплённые фото попадают в `photos_attached` результата «для врача»
и НЕ меняют score/conditions/diet (покрыто тестами).

### Хранение фото и retention (TASK-012)

- EXIF/XMP вырезаются ДО сохранения (GPS/устройство = PII). JPEG: APP1/COM-сегменты
  дропаются на уровне байтов (без перекодирования — декодированные пиксели бит-идентичны).
  WebP: EXIF/XMP RIFF-чанки дропаются (пиксели бит-идентичны). PNG: lossless-пересохранение
  без ancillary-чанков (пиксели бит-идентичны). Проверено тестом: GPS-теги исчезают,
  хэш `tobytes()` до/после совпадает.
- Ретеншн: `PHOTO_TTL_DAYS` (default 30, clamp 1..365). Просроченные файлы (+ sidecar
  `<photo_id>.json` рядом с файлом) удаляются при старте сервера и при каждом аплоаде
  (best-effort sweep, запрос никогда не падает из-за чистки).
- Sidecar `<photo_id>.json` хранит `{quality, created_at, ext}`; in-memory `_META` ограничен
  `MAX_META_ENTRIES=1000` (evict oldest). `medi-ai/app/uploads/` — git-ignored, в Docker-образ
  не печётся (см. `.dockerignore`), в репозиторий фото не коммитятся.
- Фото НИКОГДА не влияют на скоринг/диету/спорт (только `photos_attached` «для врача»).
  Не загружайте фото лица и документов — это персональные данные (предупреждение в UI).

PAR-Q скрининг в `POST /api/sport/plan` (все флаги по умолчанию `false` = жалоб нет):

| Поле | Тип | Смысл |
|------|-----|-------|
| `parq_chest_pain` | `bool` | боль в груди при нагрузке |
| `parq_dizziness` | `bool` | головокружение/обмороки |
| `parq_joint_problem` | `bool` | проблемы с суставами |
| `parq_heart_condition` | `bool` | заболевание сердца |
| `parq_diabetes` | `bool` | диабет |
| `parq_age50_unsupervised` | `bool` | возраст 50+ без наблюдения врача |
| `parq_other` | `str` | прочий анамнез (непустой текст = положительный ответ) |

Любой положительный PAR-Q → предупреждение «допуск врача» и только низкоударные нагрузки
(ходьба/плавание/вело; бег/прыжки/интервалы исключаются).

Клинические правила:

- Диета назначается строго при патологиях ЖКТ/диабете/ожирении или по прямому запросу.
- При подозрении на хирургию/аппендицит — жёсткий запрет еды и воды до осмотра хирурга.
- Доказательная база: клинические протоколы, PubMed ID, ВОЗ.

## Контракты TASK-003

- `TriageAnswer.answer`: канон `Literal["yes","no","unsure"]`. Локализованные ответы маппятся
  в сервисе/схеме: Да/Нет/Не уверен(а), Yes/No/Not sure, Иә/Жоқ/Сенімді емеспін.
  Свободный текст (`maybe`, `да нет`, `123`) → 422 ValidationError.
- `normalize_zone`: `throat` / `горло` / `шея` → `head` (выделенной throat-зоны нет;
  вопросы берутся из head-банка `neuro_*`). До TASK-003 `throat` → `general`.
- `lang`: единый хелпер `main._resolve_lang` (+ `schemas.map_lang`) во всех триаж-роутах
  (`/api/conditions`, `/api/triage/initial`, `/api/triage/final`).
  Контракт: неизвестный/пустой `lang` → fallback `"ru"` (не 422, backward-compatible).
- CORS: whitelist из env `CORS_ORIGINS` (comma-separated, напр.
  `CORS_ORIGINS="https://app.example.com,https://example.com"`).
  Дефолт без env: `["http://localhost:8000","http://127.0.0.1:8000"]`.
  Комбинация `allow_origins=["*"] + allow_credentials=True` запрещена:
  при `"*"` credentials автоматически `False`.
- Скоринг: все `k in t` мигрированы на `_kw_hit` (word-boundary, Unicode, `ё→е`);
  `_kw_pattern` по умолчанию префикс-толерантен (`\b<kw>\w*\b`) для флексий
  (грудиной, диабетом, подвздошная, migrating) с сохранением защит
  TASK-002 (`breakfast != FAST`, `139/9 != 39`, `температура 39` только как число).

## Быстрый запуск

Требуется Python 3.10+.

```bash
cd medi-ai
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Сервер поднимется на `http://127.0.0.1:8000`:

- `GET /` — интерфейс
- `GET /docs` — Swagger-документация FastAPI

Для доступа по локальной сети:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Пример запроса

```bash
curl -X POST http://127.0.0.1:8000/api/triage/initial ^
  -H "Content-Type: application/json" ^
  -d "{\"age\": 35, \"sex\": \"male\", \"height_cm\": 180, \"weight_kg\": 85, \"body_zone\": \"живот\", \"symptoms_text\": \"боль справа внизу живота, тошнота\", \"tags\": [], \"request_diet\": false}"
```

## Переменные окружения

| Переменная | Пример | Поведение |
|------------|--------|-----------|
| `CORS_ORIGINS` | `"https://app.example.com,https://example.com"` | Whitelist CORS (comma-separated). Без env — только `http://localhost:8000` и `http://127.0.0.1:8000`. `"*"` + credentials запрещены: при `"*"` credentials автоматически `False` |
| `API_KEYS` | `"key-one,key-two"` | Ключи `X-API-Key` для `/api/*` (кроме `/api/health`). Пусто/не задан — API открыт (local dev + тесты); production ОБЯЗАН задать |
| `PHOTO_TTL_DAYS` | `"30"` | TASK-012: TTL фото в днях (default 30, clamp 1..365). Просрочка удаляется на старте + per-upload |

Лимиты запросов (slowapi, на IP клиента, в минуту):

| Эндпоинт | Лимит |
|----------|-------|
| `POST /api/triage/initial` | 30/min |
| `POST /api/triage/final` | 30/min |
| `POST /api/triage/photo` | 10/min |
| `GET /api/triage/photo/{id}` | 60/min |
| `DELETE /api/triage/photo/{id}` | 30/min |
| `POST /api/sport/plan` | 30/min |
| `GET /api/conditions` | 60/min |
| `GET /api/health` | без лимита |

Ответы всегда несут hardening-заголовки (TASK-012): `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` + базовый CSP
(`default-src 'self'`, inline `script/style` разрешены через `'unsafe-inline'`,
чтобы не ломать UI — проверено smoke-тестом `GET /` → 200 без CDN).

## Продакшн (TASK-012)

```bash
cd medi-ai
docker build -t medai:012 .
docker run --rm -p 8000:8000 -e API_KEYS="prod-secret" medai:012
```

- База `python:3.12-slim`, non-root `appuser (10001)`, `uvicorn --workers 2`, без `--reload`.
- `__main__` слушает только `127.0.0.1` без reload (LAN — только через Docker `-p` / reverse proxy).
- Фронт без CDN: `app/static/tailwind.css` — вендоренный pinned-билд (значения Tailwind v3.4),
  страница рендерится офлайн-идентично; `index.html` больше не грузит `cdn.tailwindcss.com`.
- Серверные данные в UI вставляются только через `textContent`/`createElement`
  (XSS-hardening); `href` источников — только `http(s)`, иначе дропается.

## Коды ошибок

Тела 500/422 — всегда generic-тексты (без трейсбеков, путей и внутренностей; детали только в server logs).

| Код | Когда |
|-----|-------|
| `400` | недопустимый тип фото (не jpeg/png/webp) |
| `401` | нет/неверный `X-API-Key` (когда задан `API_KEYS`) |
| `404` | `/api/*` — эндпоинт не найден; неизвестный `photo_id` в `GET/DELETE /api/triage/photo/{id}` |
| `413` | фото больше 8 МБ (ранний Content-Length pre-check + точный чанковый кап) |
| `422` | ошибка валидации (generic-текст); свободный текст ответа вместо yes/no/unsure; `photo_ids` > 3 или неизвестный `photo_id`; изображение не читается / больше 40 Мпикс |
| `429` | превышен rate limit |
| `500` | неожиданная ошибка движка (generic-текст, полный трейсбек в логах) |

## Quality gates (TASK-010)

```bash
python -m ruff check medi-ai            # blocking, default ruleset, 0 warnings
python -m mypy medi-ai/app/domain medi-ai/app/services   # strict
python -m pytest --cov=medi-ai/app --cov-report=term-missing --cov-fail-under=85
```

Конфиги — `pyproject.toml` (`testpaths`, `pythonpath`, ruff `line-length = 127`, mypy strict-override).
CI (`.github/workflows/python-package.yml`, `setup-python@v5`, Python 3.10–3.12): ruff → mypy → pytest,
все шаги блокирующие (flake8 `--exit-zero` удалён).

## Дисклеймер

MediAI — инструмент предварительной оценки и не заменяет очный осмотр врача.
При жизнеугрожающих симптомах (боль в груди > 15 минут, FAST-признаки инсульта,
кровотечение, анафилаксия, острая хирургическая боль) вызывайте скорую: 103/112.
