# CHANGELOG (from git history, TASK-002 → TASK-010)

## TASK-010 — Quality configs + CI gates + docs (2026-09-23)
- `pyproject.toml`: pytest (`testpaths`, `pythonpath`), ruff (`line-length 127`,
  `target py310`), mypy strict-override for `app/domain` + `app/services`.
- `medi-ai/tests/conftest.py`: `client` + `tmp_upload_dir` fixtures.
- Removed all 8 `sys.path.insert` hacks (replaced by `pythonpath` setting).
- CI: `setup-python@v3` → `@v5`; flake8 `--exit-zero` steps replaced by blocking
  `ruff check` → `mypy` (strict, domain/services) → `pytest --cov-fail-under=85`
  (`pytest-cov` added to the install step).
- Fixed self-comparison `ru == ru` in `test_sport_hardening.py:184` (real RU/EN/KZ parity).
- Docs: README (photo endpoint, PAR-Q, env + error-code tables), `.env.example`,
  `CONTRIBUTING.md`.

## TASK-009 — P0 security bundle (2026-09-23, `89c9370`)
- Generic client error bodies (500/422/429/401) + full tracebacks in server logs only.
- Input limits: `symptoms_text` ≤ 4000, tags ≤ 20×64; streamed chunked upload with exact
  8 MB cap (413); 40 MP pixel cap (DecompressionBomb escalated to error).
- Sync photo endpoint (FastAPI threadpool, no event-loop blocking on Pillow).
- `X-API-Key` auth (`API_KEYS` env, constant-time compare; `/api/health` + OPTIONS open;
  open-by-default when unset) + slowapi rate limits on `/api/*`.

## TASK-008 — Photo upload envelope (2026-09-23, `c81642d`)
- `POST /api/triage/photo` (B4-variant-1): jpeg/png/webp ≤ 8 MB →
  `{photo_id, quality, hint}`; quality is a Pillow-only capture hint
  (`ok` | `too_dark` | `too_blurry`), no ML, no diagnosis.
- `photo_ids` (≤ 3, UUID) in `POST /api/triage/final` → `photos_attached` "for the doctor";
  photos MUST NOT change score/conditions/diet (asserted).
- `medi-ai/app/uploads/` git-ignored; private orchestrator plan guarded from commits.

## TASK-007 — Sport hardening (2026-09-23, `6e62e07`)
- BMI ban ≥ 30 (contraindication text + swim/bike training swap).
- PAR-Q gate: any positive flag → doctor-clearance warning + low-impact only.
- Documented other-sex BMR (mean of Mifflin-St Jeor male/female constants, −78).
- Realism caps (weekly loss / monthly gain) + honest wording in every goal × lang.
- RU/EN/KZ numeric parity.

## TASK-006 — Tone presets + stages (2026-09-23, `0736c5e`)
- Neutral tone + complaint presets + honest staged triage UX (one-by-one questions,
  framing block ru/en/kz, no fake timers, no sycophantic/alarmist copy).

## TASK-005 — CI fix (2026-09-23, `92ef68b`)
- Workflow installs `medi-ai/requirements.txt`, runs `medi-ai/tests/`, Python 3.10–3.12.

## TASK-004 — Honest outputs (2026-09-23, `f34203f`)
- `RULES_VERSION` 1.1, `score_breakdown` transparency, qualitative likelihood bands,
  consent gate, how-we-counted (no raw % in user-facing text).

## TASK-003 — Split contracts (2026-09-23, `6597d05`)
- God object split: `app/domain/` (catalog, questions, rules) + `app/services/`
  (`triage_service`); `triage_engine.py` kept as backward-compat re-export shim.
- Strict answer contract (`Literal["yes","no","unsure"]`, localized mapping, free text → 422).
- `throat`/`горло`/`шея` → `head` zone; unified `_resolve_lang` fallback to `ru`.
- CORS whitelist from `CORS_ORIGINS`; word-boundary Unicode scoring (`_kw_hit`).

## TASK-002 — Triage safety (2026-09-23, `f0a6424`)
- Word-boundary keyword scoring (`breakfast != FAST`, `139/9 != 39`,
  `температура 39` only as a number); any-zone fasting for GI bleed; safety tests.
