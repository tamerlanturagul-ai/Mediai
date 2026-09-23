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
│   ├── triage_engine.py     # Shim ре-экспорта (TASK-003); логика в domain//services
│   ├── domain/
│   │   ├── catalog.py       # RU/EN/KZ каталоги заболеваний
│   │   ├── questions.py     # Банки 6 зон × 3 языка
│   │   └── rules.py         # _normalize_med_text, _kw_pattern/_kw_hit/_keyword_score, _surgery_suspected, пороги
│   ├── services/
│   │   └── triage_service.py# evaluate_final, builders
│   ├── sport_engine.py      # Расчёт спорта: темп, сроки, противопоказания
│   └── static/
│       └── index.html       # Главная страница
└── requirements.txt     # fastapi, uvicorn, pydantic, httpx
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

## Дисклеймер

MediAI — инструмент предварительной оценки и не заменяет очный осмотр врача.
При жизнеугрожающих симптомах (боль в груди > 15 минут, FAST-признаки инсульта,
кровотечение, анафилаксия, острая хирургическая боль) вызывайте скорую: 103/112.
