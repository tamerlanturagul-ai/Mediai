"""Triage service: evaluate_final + builders (extracted from triage_engine, TASK-003)."""
from __future__ import annotations

from typing import Any

from ..domain.rules import (
    RULES_VERSION,
    _answer_is_positive,
    _answer_is_unsure,
    _gi_diabetes_obesity_context,
    _keyword_score_detailed,
    _kw_hit,
    _normalize_med_text,
    _surgery_suspected,
    bmi_category,
    calc_bmi,
    likelihood_label,
    normalize_zone,
    triage_level_from_score,
)
from ..i18n import (
    KW_ABD_DIAB,
    KW_FAST_HINT,
    KW_GEN_FEVER,
    KW_SURG_HINT,
    LIST_MESSAGES,
    MESSAGES,
    resolve_lang,
)
from ..schemas import (
    DietInfo,
    EvidenceSource,
    ProbableCondition,
    TriageFinalRequest,
    TriageInitialRequest,
)


def _text(req: TriageInitialRequest | TriageFinalRequest) -> str:
    parts = [req.body_zone or "", req.symptoms_text or "", " ".join(req.tags or [])]
    return " ".join(parts).lower()


def evaluate_final(req: TriageFinalRequest) -> dict[str, Any]:
    t = _text(req)
    lang = resolve_lang(getattr(req, "lang", "ru"))
    zone = normalize_zone(req.body_zone)
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    bmi_cat = bmi_category(bmi, lang)

    # --- базовый скоринг ---
    score = 0.0
    reasons: list[str] = []
    breakdown: list[dict[str, Any]] = []

    kw_score, kw_flags, kw_breakdown = _keyword_score_detailed(t)
    score += kw_score
    reasons.extend(kw_flags)
    breakdown.extend(kw_breakdown)

    # Ответы на 3 вопроса: каждый «Да» сильно повышает риск.
    positives = sum(1 for a in req.answers if _answer_is_positive(a.answer))
    # Вес зависит от зоны: для груди/головы/живота выше.
    weight_map = {"chest": 18, "head": 18, "abdomen": 16, "skin": 12, "limb": 12, "general": 14}
    w = weight_map.get(zone, 14)
    if positives:
        pts = positives * w
        score += pts
        reasons.append(f"положительных ответов на уточняющие вопросы: {positives}/3")
        breakdown.append({"reason": f"положительных ответов на уточняющие вопросы: {positives}/3", "points": float(pts)})

    # Возраст
    if req.age >= 65:
        score += 10
        reasons.append("возраст ≥65")
        breakdown.append({"reason": "возраст ≥65", "points": 10.0})
    elif req.age >= 50:
        score += 5
        breakdown.append({"reason": "возраст 50–64", "points": 5.0})

    # ИМТ
    if bmi >= 30:
        score += 8
        reasons.append(f"ИМТ {bmi} (ожирение)")
        breakdown.append({"reason": f"ИМТ {bmi} (ожирение)", "points": 8.0})
    elif bmi >= 25:
        score += 3
        breakdown.append({"reason": f"ИМТ {bmi} (избыточная масса тела)", "points": 3.0})

    # Неопределённость («не уверен») — небольшой плюс к осторожности
    unsure = sum(1 for a in req.answers if _answer_is_unsure(a.answer))
    if unsure:
        score += unsure * 4
        breakdown.append({"reason": f"неуверенных ответов: {unsure}/3", "points": float(unsure * 4)})

    score = max(0.0, min(100.0, round(score, 1)))
    level = triage_level_from_score(score)

    probable = _build_probable_conditions(zone, t, req, positives, bmi, lang)
    diet = _build_diet(zone, t, probable, req.request_diet, bmi, lang)
    actions, see_doctor, emergency_call, forbidden = _build_actions(level, zone, probable, t, lang)
    evidence = _build_evidence(zone, probable, lang)

    return {
        "bmi": bmi,
        "bmi_category": bmi_cat,
        "risk_score": score,
        "triage_level": level,
        "probable_conditions": probable,
        "diet": diet,
        "actions": actions,
        "see_doctor": see_doctor,
        "emergency_call": emergency_call,
        "forbidden_actions": forbidden,
        "evidence_sources": evidence,
        "_debug_reasons": reasons,
        "score_breakdown": breakdown,
        "rules_version": RULES_VERSION,
    }

def _build_probable_conditions(
    zone: str, t: str, req: TriageFinalRequest, positives: int, bmi: float, lang: str = "ru"
) -> list[ProbableCondition]:
    lang = resolve_lang(lang)
    tn = _normalize_med_text(t)
    cands: list[ProbableCondition] = []

    def add(name: str, icd10: str, prob: float, reason: str) -> None:
        cands.append(ProbableCondition(
            name=name, icd10=icd10,
            probability=float(max(5.0, min(95.0, round(prob, 1)))),
            reason=reason,
        ))

    def msg(key: str) -> str:
        return MESSAGES[key][lang]

    if zone == "chest":
        base = 20 + positives * 15
        add(msg("prob_chest_acs_name"), "I20–I21", base + 15, msg("prob_chest_acs_reason"))
        add(msg("prob_chest_hyp_name"), "I10", 30 + positives * 5, msg("prob_chest_hyp_reason"))
        add(msg("prob_chest_gerd_name"), "K21", 25, msg("prob_chest_gerd_reason"))
    elif zone == "abdomen":
        surg_hint = any(_kw_hit(k, tn) for k in KW_SURG_HINT[lang])
        base = 20 + positives * 14
        if surg_hint or positives >= 2:
            add(msg("prob_abd_app_name"), "K35", base + 15, msg("prob_abd_app_reason"))
            add(msg("prob_abd_chole_name"), "K80", base, msg("prob_abd_chole_reason"))
        else:
            add(msg("prob_abd_gastr_name"), "K29", base + 10, msg("prob_abd_gastr_reason"))
            add(msg("prob_abd_ulcer_name"), "K25", base, msg("prob_abd_ulcer_reason"))
        add(msg("prob_abd_ibs_name"), "K59", 25, msg("prob_abd_ibs_reason"))
        if bmi >= 30 or any(_kw_hit(k, tn) for k in KW_ABD_DIAB[lang]):
            add(msg("prob_abd_diab_name"), "E11", 30, msg("prob_abd_diab_reason"))
    elif zone == "head":
        fast_hint = any(_kw_hit(k, tn) for k in KW_FAST_HINT[lang])
        if fast_hint or positives >= 1:
            add(msg("prob_head_stroke_name"), "I63/I64", 35 + positives * 15, msg("prob_head_stroke_reason"))
        add(msg("prob_head_migr_name"), "G43", 40 if not fast_hint else 25, msg("prob_head_migr_reason"))
        add(msg("prob_head_tension_name"), "G44.2", 35, msg("prob_head_tension_reason"))
    elif zone == "skin":
        add(msg("prob_skin_cell_name"), "L03", 30 + positives * 12, msg("prob_skin_cell_reason"))
        add(msg("prob_skin_abs_name"), "L02", 30 + positives * 8, msg("prob_skin_abs_reason"))
        add(msg("prob_skin_atop_name"), "L20", 28, msg("prob_skin_atop_reason"))
    elif zone == "limb":
        add(msg("prob_limb_dorso_name"), "M54", 35 + positives * 8, msg("prob_limb_dorso_reason"))
        add(msg("prob_limb_injury_name"), "S80–S89", 30, msg("prob_limb_injury_reason"))
        add(msg("prob_limb_dvt_name"), "I80", 20 + positives * 10, msg("prob_limb_dvt_reason"))
    else:
        add(msg("prob_gen_r69_name"), "R69", 30 + positives * 10, msg("prob_gen_r69_reason"))
        if any(_kw_hit(k, tn) for k in KW_GEN_FEVER[lang]):
            add(msg("prob_gen_ari_name"), "J06", 35, msg("prob_gen_ari_reason"))
        if bmi >= 30:
            add(msg("prob_gen_obesity_name"), "E66", 40, msg("prob_gen_obesity_reason").format(bmi=bmi))

    # Сортируем по вероятности и отдаём топ-3
    cands.sort(key=lambda c: c.probability, reverse=True)
    # Нормировка не требуется — это независимые оценки; просто ограничиваем топ-3
    return cands[:3]

def _build_diet(
    zone: str, t: str, probable: list[ProbableCondition], requested: bool, bmi: float, lang: str = "ru"
) -> DietInfo:
    lang = resolve_lang(lang)
    tn = _normalize_med_text(t)

    def msg(key: str) -> str:
        return MESSAGES[key][lang]

    def msgs(key: str) -> list[str]:
        return list(LIST_MESSAGES[key][lang])

    # Жёсткий запрет при подозрении на хирургию / кровотечение
    if _surgery_suspected(zone, t, probable):
        return DietInfo(
            allowed=False,
            regime=msg("diet_surg_regime"),
            reason=msg("diet_surg_reason"),
            forbidden=msgs("diet_surg_forbidden"),
            warning=msg("diet_surg_warning"),
        )

    if _gi_diabetes_obesity_context(t, probable, bmi) or requested:
        diabetes = any("E11" in p.icd10 for p in probable) or any(_kw_hit(k, tn) for k in ["диабет", "diabetes", "қант"])
        if diabetes:
            return DietInfo(
                allowed=True,
                regime=msg("diet_diab_regime"),
                reason=msg("diet_diab_reason"),
                recommended=msgs("diet_diab_recommended"),
                forbidden=msgs("diet_diab_forbidden"),
                menu_example=msgs("diet_diab_menu"),
            )
        return DietInfo(
            allowed=True,
            regime=msg("diet_gentle_regime"),
            reason=msg("diet_gentle_reason"),
            recommended=msgs("diet_gentle_recommended"),
            forbidden=msgs("diet_gentle_forbidden"),
            menu_example=msgs("diet_gentle_menu"),
        )

    return DietInfo(
        allowed=False,
        regime=msg("diet_none_regime"),
        reason=msg("diet_none_reason"),
        recommended=msgs("diet_none_recommended"),
        forbidden=[],
    )

def _build_actions(
    level: str, zone: str, probable: list[ProbableCondition], t: str, lang: str = "ru"
) -> tuple[list[str], str, bool, list[str]]:
    lang = resolve_lang(lang)
    top = probable[0] if probable else None

    def msg(key: str) -> str:
        return MESSAGES[key][lang]

    doctor_map = {z: msg(f"doctor_{z}") for z in ("chest", "abdomen", "head", "skin", "limb", "general")}
    see_doctor = doctor_map.get(zone, doctor_map["general"])
    emergency = level in ("ORANGE", "RED")

    actions: list[str] = []
    if level == "RED":
        actions += [msg("act_red_1"), msg("act_red_2"), msg("act_red_3"), msg("act_red_4"),
                    msg("act_red_5").format(see_doctor=see_doctor)]
    elif level == "ORANGE":
        actions += [msg("act_orange_1"), msg("act_orange_2"), msg("act_orange_3"),
                    msg("act_orange_4").format(see_doctor=see_doctor)]
    elif level == "YELLOW":
        actions += [msg("act_yellow_1"), msg("act_yellow_2"),
                    msg("act_yellow_3").format(see_doctor=see_doctor)]
    else:
        actions += [msg("act_green_1"), msg("act_green_2"),
                    msg("act_green_3").format(see_doctor=see_doctor)]

    if top:
        band = likelihood_label(top.probability, lang)
        actions.append(msg("act_top_line").format(band=band, name=top.name, icd=top.icd10))

    forbidden = list(LIST_MESSAGES["forbid_list"][lang])
    if _surgery_suspected(zone, t, probable):
        forbidden.insert(0, msg("forbid_surgery"))

    return actions, see_doctor, emergency, forbidden

def _build_evidence(zone: str, probable: list[ProbableCondition], lang: str = "ru") -> list[EvidenceSource]:
    lang = resolve_lang(lang)
    who_title = MESSAGES["ev_who"][lang]
    heart_title = MESSAGES["ev_heart"][lang]
    base: list[EvidenceSource] = [
        EvidenceSource(title=who_title,
                       url="https://www.who.int/publications", type="WHO"),
        EvidenceSource(title=heart_title,
                       url="https://pubmed.ncbi.nlm.nih.gov/23465250/", type="PubMed"),
    ]
    zone_evidence = {
        "chest": EvidenceSource(
            title="ESC Guidelines — острый коронарный синдром без подъёма ST",
            url="https://www.escardio.org/Guidelines", type="Protocol"),
        "abdomen": EvidenceSource(
            title="WSES Guidelines — острый аппендицит (PMID: 32295644)",
            url="https://pubmed.ncbi.nlm.nih.gov/32295644/", type="Protocol"),
        "head": EvidenceSource(
            title="AHA/ASA Guidelines — раннее ведение острого ишемического инсульта (PMID: 31662037)",
            url="https://pubmed.ncbi.nlm.nih.gov/31662037/", type="Protocol"),
        "skin": EvidenceSource(
            title="IDSA Guidelines — инфекции кожи и мягких тканей (PMID: 24947530)",
            url="https://pubmed.ncbi.nlm.nih.gov/24947530/", type="Protocol"),
        "limb": EvidenceSource(
            title="NICE NG89 — венозная тромбоэмболия: диагностика и ведение",
            url="https://www.nice.org.uk/guidance/ng89", type="Protocol"),
        "general": EvidenceSource(
            title="PubMed — qSOFA/сепсис-скрининг (ID: 26903335)",
            url="https://pubmed.ncbi.nlm.nih.gov/26903335/", type="PubMed"),
    }
    specific = zone_evidence.get(zone)
    out = [base[0]]
    if specific:
        out.append(specific)
    out.append(base[1])
    return out[:3]
