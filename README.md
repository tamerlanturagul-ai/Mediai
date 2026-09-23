# MediAI — интеллектуальная платформа первичного клинического триажа

MediAI анализирует симптомы своими словами, зону тела и профиль пользователя (возраст, пол, рост, вес),
проводит первичный скрининг через 3 уточняющих вопроса для исключения острых состояний,
оценивает риски по шкале срочности, возвращает вероятные диагнозы с кодами МКБ-10,
лечебное питание, пошаговый план действий и ссылки на доказательную медицину.
Отдельный модуль рассчитывает безопасный спортивный план с реалистичными сроками.

Стек: Python (FastAPI + Uvicorn + Pydantic) + статический фронтенд (HTML/JS/Tailwind CSS).

## Структура проекта

```text
medi-ai/
├── app/
│   ├── main.py              # FastAPI-сервер, роуты, CORS, статика
│   ├── schemas.py           # Pydantic-модели валидации
│   ├── security.py          # API_KEYS auth + slowapi rate limits (TASK-009)
│   ├── triage_engine.py     # Shim ре-экспорта (TASK-003); логика в domain//services
│   ├── domain/
│   │   ├── catalog.py       # RU/EN/KZ каталоги заболеваний
│   │   ├── questions.py     # Банки 6 зон × 3 языка
│   │   └── rules.py         # _normalize_med_text, _kw_pattern/_kw_hit/_keyword_score, _surgery_suspected, пороги
│   ├── services/
│   │   ├── triage_service.py# evaluate_final, builders
│   │   └── photo_service.py # хранение фото + Pillow-оценка качества (TASK-008)
│   ├── sport_engine.py      # Расчёт спорта: темп, сроки, противопоказания, PAR-Q
│   ├── uploads/             # загруженные фото (git-ignored, никогда не коммитить)
│   └── static/
│       └── index.html       # Главная страница
├── tests/
│   ├── conftest.py          # fixtures: client, tmp_upload_dir (TASK-010)
│   └── test_*.py            # 8 модулей, 280 тестов
└── requirements.txt     # fastapi, uvicorn, pydantic, httpx, pillow, python-multipart, slowapi
```

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/` | Главная страница `app/static/index.html` |
| `GET` | `/api/health` | Проверка состояния сервиса |
| `GET` | `/api/conditions` | Каталог заболеваний для мега-меню: кардиология, гастроэнтерология, неврология, дерматология, хирургия (с кодами МКБ-10) |
| `POST` | `/api/triage/initial` | Первичный скрининг. Принимает профиль, зону тела, текст симптомов, теги и флаг запроса диеты. Возвращает ровно 3 уточняющих вопроса |
| `POST` | `/api/triage/final` | Финальная оценка. Возвращает ИМТ, `triage_level` (GREEN 0–25% / YELLOW 26–60% / ORANGE 61–85% / RED 86–100%), `probable_conditions` с МКБ-10, `diet`, `actions`, `evidence_sources` |
| `POST` | `/api/sport/plan` | Безопасный темп трансформации тела, физиологичные сроки, противопоказания (запрет ударного бега при ИМТ > 30) |
| `POST` | `/api/triage/photo` | Фото-конверт для врача (TASK-008, B4-variant-1). Multipart `file`: jpeg/png/webp до 8 МБ, лимит 40 Мпикс. Возвращает `{photo_id, quality, hint}`, где `quality` — только подсказка качества съёмки (`ok` \| `too_dark` \| `too_blurry` \| `unknown`, Pillow-эвристики, без ML и без диагноза). Фото НИКОГДА не влияет на скоринг |

Фото-конверт: `photo_id` (UUID) из `/api/triage/photo` передаётся в `photo_ids` (`POST /api/triage/final`, максимум 3 шт.).
Неизвестный `photo_id` → 422. Прикреплённые фото попадают в `photos_attached` результата «для врача»
и НЕ меняют score/conditions/diet (покрыто тестами).

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

Лимиты запросов (slowapi, на IP клиента, в минуту):

| Эндпоинт | Лимит |
|----------|-------|
| `POST /api/triage/initial` | 30/min |
| `POST /api/triage/final` | 30/min |
| `POST /api/triage/photo` | 10/min |
| `POST /api/sport/plan` | 30/min |
| `GET /api/conditions` | 60/min |
| `GET /api/health` | без лимита |

## Коды ошибок

Тела 500/422 — всегда generic-тексты (без трейсбеков, путей и внутренностей; детали только в server logs).

| Код | Когда |
|-----|-------|
| `400` | недопустимый тип фото (не jpeg/png/webp) |
| `401` | нет/неверный `X-API-Key` (когда задан `API_KEYS`) |
| `404` | `/api/*` — эндпоинт не найден |
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
