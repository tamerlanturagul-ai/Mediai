# DESIGN.md — MediAI UI spec (**CLINICAL CONSOLE**). STATUS: IMPLEMENTED, TASK-024 full rework.

> Single source of truth for the look. This file describes the code that ships on
> branch `task/024-rework-workbuddy`; if code and doc disagree, the code is wrong —
> fix one of them in the same commit.
> Supersedes: the ARENA-MINIMAL direction (`task/020`/`021`/`023`, never merged to
> `main`) and the rejected serif/no-icons direction of `task/014`. This rework starts
> from `origin/main` (0bd05c2) and replaces the whole visual layer.
>
> **Hard constraints (unchanged):** backend untouched (`app/*.py`, `domain/`,
> `services/`, `tests/`, `Dockerfile`, CI); flow order + gating fixed (profile → zone →
> symptoms → initial → 3 questions → consent → final → result → sport → photo;
> `finalBtn` needs 3 answers **and** consent); `data-zone` / `data-tag` **values** stay
> Russian (backend `normalize_zone`); preset **fill texts** stay RU (RU-first scoring);
> answers map to `yes`/`no`/`unsure`; offline (no CDN, no external fonts/scripts/icons);
> server strings only via `textContent`/`createElement`, `href` allowlisted to http(s);
> `uploads/`, `.env`, photos, `*DO_NOT_COMMIT*` never committed.

## 0. Direction (clinical console: quiet, dense, legible)

- Light only. Sans only. **One accent (teal) + semaphore colours reserved for triage risk.**
- **Legibility is the brief**: 16px body at 1.6 line-height, 16–17px card titles, a
  display hero, and tabular numerals on every number a jury will read from 2 m.
- Hierarchy comes from size / weight / space / hairlines — never from colour volume,
  gradients, or card shadows.
- The page reads as a **console**: a hero that states the promise, a step rail that is
  the only progress model, a two-column workspace (intake ▸ consult), then the result
  as the peak, then sport, then the evidence footer.
- Tone: competent, humane, non-alarming. No stock imagery, no emoji, no playful copy.
- Signature: paper-tinted page + hairline white cards + teal accent + Lucide line icons
  + honest motion (every animation is tied to a real fetch or a real value).

## 1. Tokens

```css
:root{
  /* surfaces */
  --bg:#f4f6f9; --bg-tint:#eef2f6; --surface:#ffffff; --surface-2:#f8fafc;
  /* ink */
  --ink:#0f172a; --ink-2:#334155; --muted:#64748b; --muted-2:#94a3b8;
  /* lines */
  --line:#e2e8f0; --line-2:#cbd5e1; --line-strong:#94a3b8;
  /* accent (clinical teal) */
  --accent:#0f766e; --accent-deep:#115e59; --accent-tint:#f0fdfa; --accent-line:#99f6e4;
  --ring:0 0 0 2px #fff, 0 0 0 4px rgba(15,118,110,.45);
  /* semantic states */
  --danger:#b91c1c; --danger-fill:#dc2626; --danger-tint:#fef2f2; --danger-line:#fecaca;
  --warn:#b45309;   --warn-tint:#fffbeb;   --warn-line:#fde68a;
  --ok:#047857;     --ok-tint:#ecfdf5;     --ok-line:#a7f3d0;
  /* triage semaphore — risk ONLY */
  --lvl-green:#16a34a; --lvl-green-tint:#ecfdf5;
  --lvl-yellow:#facc15; --lvl-yellow-ink:#713f12;
  --lvl-orange:#ea580c; --lvl-orange-tint:#fff7ed;
  --lvl-red:#dc2626;   --lvl-red-tint:#fef2f2;
  /* geometry */
  --r-card:16px; --r-box:12px; --r-input:10px; --r-pill:999px;
  --w-page:1200px; --w-read:72ch;
  /* type */
  --font-body:'Golos Text',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  --font-mono:ui-monospace,'Cascadia Mono',SFMono-Regular,Menlo,Monaco,Consolas,monospace;
  /* motion */
  --ease:cubic-bezier(.2,.7,.3,1); --t-fast:120ms; --t-med:180ms; --t-slow:260ms;
  /* elevation — popovers only; cards stay hairline (no card shadows anywhere) */
  --pop:0 12px 32px -8px rgba(15,23,42,.18), 0 2px 8px -2px rgba(15,23,42,.08);
}
```

- **Colour usage.** `--bg` page; `--surface` cards/inputs/chips/ai-bubbles/popovers;
  `--surface-2` inset boxes (chat canvas, map wrap, `.note`, `.box`, `#howCounted`,
  sport stats); `--ink` body text, user bubbles, selected chips, active language,
  risk marker, primary buttons are `--accent`; `--muted`/`--muted-2` secondary text,
  captions, placeholders; `--line` every hairline, `--line-2` hover borders,
  `--line-strong` checkbox outline. `--accent-tint`/`--accent-line` mark selected-but-not-
  primary surfaces (eyebrow, "done" step, file button, zone active tint). `--lvl-*` is
  used **only** by `#triageBadge`, the semaphore bar and `.framing[data-kind]`.
- **Type.** Golos Text 400/500/600 (OFL-1.1), vendored under
  `medi-ai/app/static/fonts/*.woff2` with `@font-face` + `unicode-range` (cyrillic +
  latin subsets, `font-display:swap`). Mono = system stack, never a webfont.
  Weights: 400 body · 500 labels/buttons/chips · 600 titles/hero/numbers.
  Sizes: body **16px/1.6**; hero `clamp(1.75rem, 1.05rem + 2.6vw, 2.85rem)/1.1`,
  `letter-spacing:-.028em`; hero sub `clamp(1rem, .94rem + .3vw, 1.125rem)`;
  card titles 15px/600 `-.01em`; question text 15px/500; inputs 15px;
  chat + lists 14px; captions/hints 12–13px; mono captions 11px with
  `letter-spacing:.08–.14em` + uppercase. `.tnum` (tabular numerals) on every
  `#riskScore`, `#bmiVal`, `#stepQpos`, `#rulesVer`, `.sport-stat .v`, scale ticks.
- **Spacing.** 4 = inline icon/text gaps (`gap:4–6px`); 8 = chip rows, tool gaps;
  10–12 = field padding, inset boxes, grid gaps inside a card; 14 = card header to body;
  16 = column gap (`--cols gap`) and page gutter; 20 = card padding (`padding:20px`);
  22–26 = hero / footer rhythm; 30–38 = hero block. Card padding is 20px exactly.
- **Radii.** card 16px · inset box 12px · input/button 10px · chip/pill 999px ·
  checkbox 6px · risk marker 3px · icon badge 7–8px.
- **Borders.** 1px `--line` on cards, chips, inputs, inset boxes, popovers, sport stats.
  Exceptions: `.em-pill` uses `--danger-line`; `.file-btn` uses `--accent-line`;
  `#howCounted` uses 1px `--line` **plus a 3px `--accent` left rule**;
  `.framing` uses a 3px left rule whose colour is the level/kind.
- **Shadows.** `box-shadow:none` on all cards. `--pop` is used only by `#megaMenu`
  and `#plusMenu`. `#riskMarker` carries `0 0 0 2px #fff` to separate it from any
  semaphore segment.
- **Icons.** Inline `<symbol>` sprite in `index.html` (`#sprite`, `display:none`),
  `stroke:currentColor`, `fill:none`, `viewBox 0 0 24 24`, `stroke-width:2`,
  round caps/joins, Lucide paths (MIT). 21 symbols: `activity`, `messages`, `user`,
  `pin`, `camera`, `dumbbell`, `alert`, `check`, `x`, `chevron`, `lang`, `reset`,
  `sparkles`, `file`, `pulse`, `send`, `info`, `shield`, `clipboard`, `scale`, `book`,
  `utensils`, `plus`, `ban`, `arrow-right`. Sizes: `.ic` 16px inline, `.ic-lg` 18px
  section markers, `.ic-xl` 22px. Static icons are authored as `<svg class="ic">…<use>`;
  dynamic ones are built by `iconEl(name, cls)` which also sets `aria-hidden`.
  **`data-i18n` never sits on an element that also contains an `<svg>`** — the label
  lives in an inner `<span>`, otherwise `applyI18n()` wipes the icon.

## 2. Layout

- Page shell `.page`: `max-width:1200px`, `margin:0 auto`, `padding:0 16px 40px`.
- `.cols`: 1 column; **≥1120px → `minmax(0,5fr) minmax(0,7fr)`** (intake ▸ consult),
  `gap:16px`, `align-items:start`. Below 1120px the columns stack in DOM order.
- **Section order (DOM = mobile order):** header → hero → step rail → intake column
  (profile → body zone + presets → photo) → consult column (chat + questions + consent +
  final → result) → sport → footer.
- **Why photo is in the intake column.** The contract lists photo last, but
  `photo_ids` travel with `POST /api/triage/final`, so the control must be reachable
  *before* the final button. Placement is visual only; the flow position is unchanged
  and the card is badged "необязательно" (dashed `card-n.opt`), not numbered.
- Header `.hdr`: sticky `top:0`, `z-index:40`, `rgba(255,255,255,.9)` +
  `backdrop-filter: blur(12px)`, 1px `--line` bottom border.
  - **≥640px, one row:** `[brand][tagline ≥1000px] ……… [nav links][emergency pill][lang]`
    (`order:1 brand / 2 tagline / 3 nav / 4 tools`).
  - **<640px, exactly two rows:** row 1 = brand + emergency pill + language segmented
    control (language icon hidden, `margin-left:auto`); row 2 = full-width nav strip
    (`.nav{width:100%; flex-wrap:nowrap; overflow-x:auto}`) with the short catalog
    caption (`.only-sm` = "Каталог") and "Источники" hidden (`.nav-hide-sm`).
    Verified `documentElement.scrollWidth === clientWidth` at **360px**.
- Card grid: `.grid2` (2 fields), `.rows` (chips), `.rows-grid` 2→3 col,
  `.rows-zones` 2→3→2 col, `.cols2` 1→2 col (≥768px).
- Hero: single column <900px; **≥900px** `minmax(0,1.55fr) minmax(0,1fr)` — promise on
  the left, "Как это работает" 3-step panel on the right.
- Footer `.foot`: `max-width:1200px`, top hairline, wraps; `#evidenceBase` is the
  always-reachable anchor for the "Источники" nav link and the hero's secondary CTA
  (the result card also has `id="evidence"`, but it is hidden until the assessment runs).

## 3. Components (anatomy · spacing · colours · states)

- **Primary buttons** (`#sendBtn`, `#finalBtn`, `#sportBtn`, `#photoUploadBtn` is
  secondary): accent fill + white text + 1px accent border + 10px radius;
  `padding:11px 20px`, 15px/500; hover `--accent-deep`; `:active scale(.97)`;
  disabled 42% + `not-allowed`; **the global in-flight guard disables every action
  button while any request is in flight** (no per-button spinner — the shared
  `#loader` dots report progress). Focus = `--ring`. `#finalBtn` is full-width.
- **Secondary chips** (`.chip`; `.tagBtn`, `.zoneBtn`, `.presetBtn`, `.ansBtn`, back,
  nav links, example chips): surface + 1px line + `--ink-2` text; hover `--surface-2`;
  `:active scale(.97)`; **selected = `is-on` → ink fill + white text** (zone buttons
  override to accent fill). Preset chips are left-aligned 2-col grid; zone chips are
  `min-height:48px` for touch. Chips are never disabled.
- **Tertiary / icon buttons**: `.btn-icon` (40px circle, `#plusBtn`), `.btn-link`
  (`#megaClose`). Destructive text only in `.photo-chip .rm` (`--danger`, hover
  `--danger-tint`) — no salmon/pink tint anywhere else.
- **Photo chips**: neutral pill (`--surface` + `--line`), mono label "фото N", action
  "✕ переснять" in `--danger`. Remove also issues `DELETE /api/triage/photo/{id}`
  best-effort; the UI splices regardless.
- **Inputs / selects**: `--surface` + 1px `--line` + 10px radius + 15px ink text;
  hover `--line-2`; focus = `--accent` border + `--ring`. Selects are native (a11y) with
  a **custom chevron drawn as an inline `data:image/svg+xml`** background — offline, no
  CDN; focus uses a single 2px accent ring. Number spinners stay native (a11y).
- **Checkboxes** (`#dietFlag`, `#consentCheck`, `#photoConsent`): `appearance:none`,
  18×18, `flex:none`, 6px radius, `--line-strong`; checked = accent fill + white inline
  SVG check (data-URI, never emoji); focus-visible = `--ring`; the label is a
  `flex items-start gap-2` row so the box never shrinks.
- **File control**: `.file-wrap` (surface + line + 10px radius, `inline-flex`) with the
  real `<input type="file">` stretched transparent on top (still keyboard-focusable),
  a non-interactive accent-outlined `.file-btn` and a truncated `#fileName` readout
  (12rem desktop / 7rem ≤639px) so the button + name + upload stay on one line at 390px.
- **Body map** (`#bodyMap`, 160×344): 8 silhouette shapes + 1 dashed "skin" halo;
  fill `--line`, hover `opacity:.72`, selected `fill:var(--accent)` (halo:
  `--accent` stroke + `--accent-tint` fill). Zone names are drawn **inside** the map as
  localized `<text data-i18n="zone_*">` labels that flip to white when active. Limbs are
  intentionally unlabelled — they are visually self-evident and the 5 chips are the
  keyboard/primary control. Chips carry the raw Russian `data-zone` values; the display
  name in `#zoneLabel` is localized via `ZONE_NAMES`.
- **Step rail** (`#steps`): three mono uppercase pills; `is-cur` = ink fill + white text
  (and `border-color:var(--ink)`, closing the old A6 backlog item); `is-done` =
  `--accent-tint` + `--accent-line` + accent text + a `check` icon. Driven **only** by
  real API progress (`setStep(1|2|3)`), never by timers.
- **Chat**: `--surface-2` canvas, 12px radius, `max-height:400px`, scroll, `gap:12px`.
  AI bubble = surface + hairline, left, `border-bottom-left-radius:6px`, with a
  `sparkles` lead icon; user bubble = ink fill + white, right, `border-bottom-right-
  radius:6px`; both `max-width:88%`, 14px. Empty state = the greeting lead bubble plus
  three example chips that call `applyPreset()` (RU fills) and scroll to the zone card.
  `#loader` dots + localized "Запрос выполняется…" appear only while a fetch is open.
- **Question card** (`.qcard`): surface + hairline + 12px + `msg-enter`; anatomy =
  mono counter ("Вопрос a из b", localized) → 15px/500 question → 12px muted reason →
  option chips → nav row (Back chip when `idx>0` + "Отвечено: n/3"). Exactly one
  question at a time; `renderQuestions()` is a kept compatibility alias.
- **Answer mapping.** Options come from the server already localized
  (Да/Нет/Не уверен(а) · Yes/No/Not sure · Иә/Жоқ/Сенімді емеспін). The UI stores the
  **canonical** literal (`ANSWER_CANON = ['yes','no','unsure']` indexed by option
  position) and sends that, so `TriageAnswer.answer` never depends on translation.
- **Result** (`#result`, `display:none` → `.is-on`): emergency banner → title (04) →
  sub → `.framing` (kind-tinted left rule via `data-kind`) → `#photosBox` → stamp row
  (`#triageBadge` + Risk `#riskScore` + BMI `#bmiVal` + `#bmiCat`) → 4-segment semaphore
  (25/35/25/15 = thresholds 25/60/85/100) with `#riskMarker` → mono ticks
  (`0 GREEN · 25 · 60 · 85 · 100 RED`) → 2-col grids (conditions / diet) → 2-col grids
  (plan + forbidden / evidence) → `#howCounted`.
  - `#triageBadge` is a mono pill driven by `data-level`; **YELLOW uses dark ink on
    `--lvl-yellow` (`#713f12` on `#facc15`, ≈6.0:1)** — this deliberately closes the
    old P0 A2 contrast defect (white on yellow ≈1.9:1).
  - `#riskScore` animates 0 → the **real** server value over 600ms via
    `requestAnimationFrame` (decoration only, never feeds logic); with
    `prefers-reduced-motion: reduce` it renders the final value instantly.
- **Menus**: `#megaMenu` (full-width, absolute under the header, 4-col ≥768px / 2-col
  below, category heads + mono ICD chips + urgency hints) and `#plusMenu` (236px popover
  above the `+`). Both use `--pop` and `pop` 120ms. Close on Esc, outside click, or
  toggle; `aria-expanded` is kept in sync.
- **Skeletons**: `.skel.animate-pulse` with `--line` bars renders only during the real
  `POST /api/triage/initial`; the sport panel shows a localized "Расчёт" line with the
  same loader dots. No fake delays anywhere.
- **Lists**: `.list` (square accent markers via `li::before`) for diet/forbidden/
  breakdown/sport; `.list.decimal` (mono accent counters) for `#actions`;
  `.list.danger` (red markers) for forbidden actions and contraindications.
- **Sport**: 2×2 → 4-col `.sport-stat` tiles (BMI / BMR / TDEE / target, tabular),
  then pace + timeline, then training / nutrition / contraindications / warnings.
- **Footer**: 12px muted copy + `#evidenceBase` block + a mono "Правила 1.1 · эвристика"
  badge.

## 4. Motion (honest only — real fetches, real values)

| Trigger | Duration | Easing | Properties |
|---|---|---|---|
| Page-load stagger (`.reveal`, 70ms steps via `--i`, once) | 420ms | `var(--ease)` | opacity + transform (rise 8px) |
| Message / question / greeting enter (`.msg-enter`, `.qcard`) | 180ms | `var(--ease)` | opacity + transform (rise 8px) |
| Risk marker slide (`#riskMarker left`) | 260ms | `var(--ease)` | left |
| Risk count-up (rAF) | 600ms fixed | ease-out cubic | `textContent` steps (real value only) |
| Press (`:active` buttons/chips) | 120ms | `var(--ease)` | `scale(.97)` |
| Menu pop (`#megaMenu`, `#plusMenu`) | 120ms | ease-out | opacity + `scale(.98→1)` |
| Skeleton pulse / loader dots | 2000ms / 1200ms | `pulse` / `bounce` | opacity, translateY |
| Selected-state colour flips (chip/zone/tag/answer/lang/step) | 120–180ms | `var(--ease)` | background + color + border-color |

- `prefers-reduced-motion: reduce` turns **all** animations and transitions off
  (`animation:none !important; transition:none !important`), forces
  `scroll-behavior:auto`, and makes `.reveal` and the count-up render their final state
  immediately.
- There is **no** `setTimeout` / `setInterval` in the page (asserted by
  `test_frontend_no_fake_timers_or_deps`); every skeleton/loader is bound to a live
  `fetch` through the `busy` counter.

## 5. i18n

- One `I18N` dict, three complete tables (`ru`/`en`/`kz`), resolved by
  `t(key)` with RU fallback; `fmt(key, vars)` does `{placeholder}` substitution.
  `applyI18n()` walks `[data-i18n]` (textContent) and `[data-i18n-ph]` (placeholder),
  sets `document.title` and the `+` button tooltip.
- **Extended for this rework** (RU/EN/KZ): `brandSub`, `skipTo`, `catalogShort`,
  `eyebrow`, `heroA/B/C`, `heroSub`, `heroCta`, `heroCta2`, `trust1–4`, `howtoTitle`,
  `howto1–3`, `zoneCaption`, `examplesTitle`, `photoOpt`, `fileBtn`, `fileEmpty`,
  `finalHint`, `finalHintReady`, `bmiCat`, `footNote`, `evBaseTitle`.
- `data-zone` / `data-tag` **values stay Russian** (backend contract); the visible
  names come from `ZONE_NAMES` and the localized chip/map labels.
- Preset **fill texts** stay Russian (scoring is RU-first); only the captions translate.
- Server payloads (questions, options, result, catalog, evidence, sport) are rendered
  exclusively through `textContent` / `createElement`; `href` passes `isSafeHttpUrl`.
- `#zoneLabel` and the map labels re-translate on language switch; the answer chips are
  rebuilt from the server's localized `options`.

## 6. Deliberate decisions & contract notes

- `tailwind.css` is **unchanged** (0 added lines): the vendored subset is still linked so
  the preflight reset (`box-sizing`, margin/padding zeroing, `button/input` font
  inheritance, `img/svg{display:block}`) applies, and `test_release` keeps asserting
  `.bg-slate-100` / `.bg-blue-600` exist in it. The new design system lives entirely in
  `index.html`'s `<style>` block and uses semantic classes + `data-*` state
  (`is-on`, `is-cur`, `is-done`, `is-active`, `data-level`, `data-kind`) instead of
  toggling Tailwind colour utilities.
- New binary assets added: `static/mark.png` (256×256, transparent, cropped from the
  existing `logo.png` mark) used for the header mark + favicon, and
  `static/favicon.png` (64×64). `logo.png` is untouched.
- `main.py`, `schemas.py`, `domain/`, `services/`, `tests/`, `Dockerfile`, CI: **not
  touched**. No new endpoints, no request/response shape changes.
- `renderResult` no longer assigns `className` strings built from server data; the
  badge level is a `data-level` attribute, and `#emergencyText` is a separate node so
  the banner icon is never wiped.

## 7. Backlog — deliberately NOT polished

| ID | Item | Why left |
|---|---|---|
| B1 | Native `<select>` option popup keeps the OS highlight | Not styleable; a custom listbox would add a11y risk under time pressure. The trigger itself is fully themed. |
| B2 | `input[type=number]` spinners stay native | Accessibility + keyboard behaviour outweigh cosmetics. |
| B3 | `.framing` and `.box` prose is not collapsed | Transparency is a product promise; no "read more" affordance yet. |
| B4 | Evidence list is a flat column | A source-type filter is a future feature, not a design fix. |
| B5 | KZ copy is machine-reviewed, not native-reviewed | Flagged for a native Kazakh pass before public launch. |
| B6 | No dark mode | Explicitly out of scope for this task. |
| B7 | Hero art is a functional 3-step panel, not an illustration | Avoids stock imagery; keeps the page offline and fast. |

## 8. Responsive proof (shots removed from repo, verified by probes)

Run against the live app (`uvicorn app.main:app`) with Chrome via Playwright,
`deviceScaleFactor:2` on mobile. Console errors, page errors and failed requests were
recorded per phase — **0 errors in all 7 phases**.

> Proof screenshots (`shot024_*`: 1440 top/result/full RU+EN+KZ, 390 top/result/full,
> 360 top) were verified during the rework and then removed from the repo to keep it
> light. Re-generate via Playwright against the live app if needed.

Overflow probes: `scrollWidth === clientWidth` at **390px** and at **360px**.

## 9. Acceptance checklist

- [x] `python -m ruff check medi-ai` → clean
- [x] `python -m mypy medi-ai/app/domain medi-ai/app/services` → clean (strict)
- [x] `python -m pytest -q` → **335 passed**
- [x] RU/EN/KZ switch translates the whole chrome (hero, rail, cards, chat, result,
      sport, footer, buttons, placeholders, titles)
- [x] Photo upload → attach → remove (incl. best-effort `DELETE`)
- [x] Double-submit guard: `busy` counter disables every action button during any request
- [x] Full reset (`#plusClear`) restores state, zones, tags, photos, result, sport
- [x] Empty states: greeting bubble + example chips; `#questions` empty; `#sportOut` hidden
- [x] Zero console errors during the RU flow
- [x] Offline: no CDN, no external fonts/scripts/icons; `grep http` in the page → only
      the inline SVG `xmlns` URIs and server-supplied evidence links
- [x] `git status --short` contains no `uploads/`, `.env`, photos, `*DO_NOT_COMMIT*`

### 9.1 Functional probe — behaviour actually driven, not just read

A Playwright probe drove the live app end to end (1440×900, real requests):
**46/46 assertions passed, 0 console errors, 0 page errors.**

| Area | Assertions |
|---|---|
| Empty states | `#questions` empty · `#result` hidden · `#sportOut` hidden · `#photoList` empty · `#finalBtn` disabled · rail at step 1 · greeting bubble present |
| Photo consent gate | upload refused with an error hint and **0** POSTs while `#photoConsent` is unticked |
| Photo upload | exactly 1 `POST /api/triage/photo`, chip appears labelled «фото 1», success hint, `#fileName` reset |
| Photo cap | 3 accepted; the 4th is refused with «Уже прикреплено 3 фото — максимум.» and issues no request |
| Photo remove | chip spliced immediately **and** `DELETE /api/triage/photo/{id}` issued → **200** |
| Double-submit guard | 3 synchronous clicks on `#sendBtn` → exactly **1** `POST /initial`; 3 on `#finalBtn` → exactly **1** `POST /final` |
| Consent gate | `#finalBtn` clicked twice without consent → **0** `POST /final` |
| Flow | rail 1 → 2 → 3; step counter reaches 3; `#riskMarker` positioned (`calc(89% - 3px)`); framing `data-kind=redflag` |
| Photos in result | `#photosBox` shows «Фото для врача, не автодиагноз (2)» with per-photo quality |
| Full reset | 15 assertions: chat back to greeting only, questions/result/sport/photos/tags cleared, zone back to `живот`, symptoms + consent + diet flag cleared, `#finalBtn` disabled, rail back to 1, marker parked, banner hidden |
| i18n after reset | switching to EN retranslates the rail, the zone label and `document.title` |
