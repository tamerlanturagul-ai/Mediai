# CONTRIBUTING

## Branch-per-task rule
- One task = one branch: `git checkout -b task/<NNN>-short-name` from `main`.
- Scope the diff to the task prompt. Do NOT touch app scoring, endpoints,
  or frontend unless the task explicitly says so.
- Private files (`_PRIVATE_PLAN_DO_NOT_COMMIT.md`, `ANTREK*.md`, `*DO_NOT_COMMIT*`,
  `medi-ai/app/uploads/`) must NEVER be committed (already git-ignored).

## Run tests / lint (from repo root, Python 3.10+)
```bash
pip install -r medi-ai/requirements.txt
pip install ruff mypy pytest pytest-cov   # quality gates (CI-only, not in requirements)

python -m pytest -q                                   # full suite (335 tests)
python -m ruff check medi-ai                          # blocking, 0 warnings
python -m mypy medi-ai/app/domain medi-ai/app/services  # strict on clinical core
python -m pytest --cov=medi-ai/app --cov-report=term-missing --cov-fail-under=85
```

## Rules
- `ruff check` must pass with no new `ignore`s: fix the code, or add an inline
  `# noqa: <RULE>  # <reason>` for genuine exceptions only
  (current: `B008` FastAPI `File(...)` idiom, `BLE001` Pillow-decode guard).
- `mypy --strict` must pass on `app/domain` and `app/services`.
- Coverage floor is 85% (`--cov-fail-under=85`); keep it green.
- Tests import via `pythonpath = ["medi-ai"]` (pyproject): never add `sys.path` hacks.
  Shared fixtures live in `medi-ai/tests/conftest.py` (`client`, `tmp_upload_dir`).
- Env template: `.env.example` documents `CORS_ORIGINS` / `API_KEYS`; never commit `.env`.
