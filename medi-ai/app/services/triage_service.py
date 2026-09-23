"""Triage service: evaluate_final + builders (extracted from triage_engine, TASK-003)."""
from __future__ import annotations

from typing import List, Tuple

from ..domain.rules import (
    RULES_VERSION,
    _answer_is_positive,
    _answer_is_unsure,
    _gi_diabetes_obesity_context,
    _keyword_score_detailed,
    _kw_hit,
    _norm_lang,
    _normalize_med_text,
    _surgery_suspected,
    bmi_category,
    calc_bmi,
    likelihood_label,
    normalize_zone,
    triage_level_from_score,
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


def evaluate_final(req: TriageFinalRequest) -> dict:
    t = _text(req)
    lang = _norm_lang(getattr(req, "lang", "ru"))
    zone = normalize_zone(req.body_zone)
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    bmi_cat = bmi_category(bmi, lang)

    # --- базовый скоринг ---
    score = 0.0
    reasons: List[str] = []
    breakdown: List[dict] = []

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
) -> List[ProbableCondition]:
    l = _norm_lang(lang)
    tn = _normalize_med_text(t)
    cands: List[ProbableCondition] = []

    def add(name: str, icd10: str, prob: float, reason: str) -> None:
        cands.append(ProbableCondition(
            name=name, icd10=icd10,
            probability=float(max(5.0, min(95.0, round(prob, 1)))),
            reason=reason,
        ))

    if l == "en":
        if zone == "chest":
            base = 20 + positives * 15
            add("Acute coronary syndrome (angina / infarction)", "I20–I21", base + 15,
                "Retrosternal pain ± radiation/dyspnea — rule out ACS")
            add("Essential hypertension", "I10", 30 + positives * 5, "Associated cardiac symptoms")
            add("GERD (cardiac mimic)", "K21", 25, "Retrosternal burning may mimic cardiac pain")
        elif zone == "abdomen":
            surg_hint = any(_kw_hit(k, tn) for k in ["справа внизу", "миграция", "подвздош", "подвздошная", "аппендицит", "твёрдый", "твердый", "right lower", "migrat", "migrating", "migration", "rigid"])
            base = 20 + positives * 14
            if surg_hint or positives >= 2:
                add("Acute appendicitis (suspected)", "K35", base + 15, "Right-sided migration + fever/nausea")
                add("Cholelithiasis / colic", "K80", base, "Abdominal pain linked to fatty food")
            else:
                add("Acute gastritis", "K29", base + 10, "Epigastric pain/discomfort")
                add("Gastric ulcer", "K25", base, "Hunger/night pain — rule out complication")
            add("Irritable bowel syndrome", "K59", 25, "Functional differential diagnosis")
            if bmi >= 30 or any(_kw_hit(k, tn) for k in ["диабет", "diabetes", "жажда"]):
                add("Type 2 diabetes (screening)", "E11", 30, "Obesity/thirst — check glucose")
        elif zone == "head":
            fast_hint = any(_kw_hit(k, tn) for k in ["перекос", "онемела", "онемение", "речь", "речи", "инсульт", "face droop", "stroke"])
            if fast_hint or positives >= 1:
                add("Suspected stroke (TIA/ischemic)", "I63/I64", 35 + positives * 15, "FAST signs — emergency care")
            add("Migraine", "G43", 40 if not fast_hint else 25, "Pulsating unilateral pain ± aura")
            add("Tension-type headache", "G44.2", 35, "Pressing bilateral pain")
        elif zone == "skin":
            add("Cellulitis / erysipelas (if spreading fast)", "L03", 30 + positives * 12, "Rapid spread + pain/fever")
            add("Skin abscess", "L02", 30 + positives * 8, "Pus/fluctuation — surgeon exam")
            add("Atopic dermatitis", "L20", 28, "Itch/chronic course — dermatologist")
        elif zone == "limb":
            add("Dorsopathy with radicular syndrome", "M54", 35 + positives * 8, "Back/limb pain ± numbness")
            add("Limb injury (bruise/strain)", "S80–S89", 30, "Linked to load/trauma")
            add("Deep vein thrombosis (rule out if one-sided edema)", "I80", 20 + positives * 10, "One-sided calf edema + calf pain")
        else:
            add("Requires in-person differentiation", "R69", 30 + positives * 10, "Nonspecific symptoms — GP exam")
            if any(_kw_hit(k, tn) for k in ["температура", "fever", "қызба"]):
                add("Acute respiratory infection", "J06", 35, "Fever + catarrhal symptoms")
            if bmi >= 30:
                add("Obesity", "E66", 40, f"BMI {bmi}")
        cands.sort(key=lambda c: c.probability, reverse=True)
        return cands[:3]

    if l == "kz":
        if zone == "chest":
            base = 20 + positives * 15
            add("Жедел коронарлық синдром (стенокардия / инфаркт)", "I20–I21", base + 15,
                "Төс артындағы ауырсыну ± иррадиация/ентігу — ЖҚС жоққа шығару")
            add("Эссенциалды гипертензия", "I10", 30 + positives * 5, "Ілеспе жүрек симптомдары")
            add("ГЭРА (жүрек ауырсынуына ұқсас)", "K21", 25, "Төс артындағы ашу жүрек ауырсынуына ұқсауы мүмкін")
        elif zone == "abdomen":
            surg_hint = any(_kw_hit(k, tn) for k in ["справа внизу", "миграция", "подвздош", "подвздошная", "аппендицит", "твёрдый", "твердый", "оң жақ"])
            base = 20 + positives * 14
            if surg_hint or positives >= 2:
                add("Жедел аппендицит (күдік)", "K35", base + 15, "Ауырсынудың оңға ығысуы + қызба/жүрек айну")
                add("Өт тас ауруы / шаншу", "K80", base, "Іш ауырсынуы, майлы тағаммен байланыс")
            else:
                add("Жедел гастрит", "K29", base + 10, "Эпигастрийде ауырсыну/жайсыздық")
                add("Асқазан жарасы", "K25", base, "Аш/түнгі ауырсыну — асқынуды жоққа шығару")
            add("Тітіркенген ішек синдромы", "K59", 25, "Функционалды ажыратпа диагноз")
            if bmi >= 30 or any(_kw_hit(k, tn) for k in ["диабет", "қант", "шөлдеу"]):
                add("2-типті қант диабеті (скрининг)", "E11", 30, "Семіздік/шөлдеу — глюкозаны тексеру")
        elif zone == "head":
            fast_hint = any(_kw_hit(k, tn) for k in ["перекос", "онемела", "онемение", "речь", "речи", "инсульт", "бет қисаюы"])
            if fast_hint or positives >= 1:
                add("Инсульт күдігі (ТИА/ишемиялық)", "I63/I64", 35 + positives * 15, "FAST белгілері — шұғыл көмек")
            add("Мигрень", "G43", 40 if not fast_hint else 25, "Аурасы бар біржақты солқылдаған ауырсыну")
            add("Кернеулі бас ауруы", "G44.2", 35, "Қысатын екіжақты ауырсыну")
        elif zone == "skin":
            add("Целлюлит / рожа (жылдам жайылса)", "L03", 30 + positives * 12, "Жылдам жайылу + ауырсыну/қызба")
            add("Тері абсцессі", "L02", 30 + positives * 8, "Ірің — хирург қарауы")
            add("Атопиялық дерматит", "L20", 28, "Қышыну/созылмалы ағым — дерматолог")
        elif zone == "limb":
            add("Түбірлік синдромы бар дорсопатия", "M54", 35 + positives * 8, "Арқа/аяқ-қол ауырсынуы ± ұю")
            add("Аяқ-қол жарақаты (соғылу/созылу)", "S80–S89", 30, "Жүктеме/жарақатпен байланыс")
            add("Терең вена тромбозы (біржақты ісікте жоққа шығару)", "I80", 20 + positives * 10, "Балтырдың біржақты ісінуі + ауырсыну")
        else:
            add("Күндізгі саралау қажет", "R69", 30 + positives * 10, "Бейспецификалық симптомдар — терапевт қарауы")
            if any(_kw_hit(k, tn) for k in ["температура", "қызба"]):
                add("Жедел респираторлық инфекция", "J06", 35, "Қызба + катаралды симптомдар")
            if bmi >= 30:
                add("Семіздік", "E66", 40, f"ДСИ {bmi}")
        cands.sort(key=lambda c: c.probability, reverse=True)
        return cands[:3]

    # ru (default, исходная логика)

    if zone == "chest":
        base = 20 + positives * 15
        add("Острый коронарный синдром (стенокардия / инфаркт)", "I20–I21", base + 15,
            "Загрудинная боль ± иррадиация/одышка — требует исключения ОКС")
        add("Эссенциальная гипертензия", "I10", 30 + positives * 5, "Связанная кардиальная симптоматика")
        add("Гастроэзофагеальный рефлюкс (кардиалгия-имитация)", "K21", 25, "Жжение за грудиной может имитировать кардиалгию")
    elif zone == "abdomen":
        surg_hint = any(_kw_hit(k, tn) for k in ["справа внизу", "миграция", "подвздош", "подвздошная", "аппендицит", "твёрдый", "твердый"])
        base = 20 + positives * 14
        if surg_hint or positives >= 2:
            add("Острый аппендицит (подозрение)", "K35", base + 15, "Миграция боли вправо + лихорадка/тошнота")
            add("Желчнокаменная болезнь / колика", "K80", base, "Боль в животе, связь с жирной пищей")
        else:
            add("Острый гастрит", "K29", base + 10, "Боль/дискомфорт в эпигастрии")
            add("Язвенная болезнь желудка", "K25", base, "Голодные/ночные боли — исключить осложнение")
        add("Синдром раздражённого кишечника", "K59", 25, "Функциональный дифференциальный диагноз")
        if bmi >= 30 or any(_kw_hit(k, tn) for k in ["диабет", "жажда"]):
            add("Сахарный диабет 2 типа (скрининг)", "E11", 30, "Ожирение/жажда — проверить глюкозу")
    elif zone == "head":
        fast_hint = any(_kw_hit(k, tn) for k in ["перекос", "онемела", "онемение", "речь", "речи", "инсульт", "слабость руки"])
        if fast_hint or positives >= 1:
            add("Подозрение на инсульт (ТIA/ишемический)", "I63/I64", 35 + positives * 15,
                "FAST-признаки — экстренная помощь")
        add("Мигрень", "G43", 40 if not fast_hint else 25, "Пульсирующая односторонняя боль ± аура")
        add("Головная боль напряжения", "G44.2", 35, "Давящая двусторонняя боль")
    elif zone == "skin":
        add("Целлюлит / рожа (подозрение при быстром распространении)", "L03",
            30 + positives * 12, "Быстрое распространение + боль/лихорадка")
        add("Абсцесс кожи", "L02", 30 + positives * 8, "Гной/флюктуация — осмотр хирурга")
        add("Атопический дерматит", "L20", 28, "Зуд/хроническое течение — дерматолог")
    elif zone == "limb":
        add("Дорсопатия с корешковым синдромом", "M54", 35 + positives * 8, "Боль в спине/конечности ± онемение")
        add("Травма конечности (ушиб/растяжение)", "S80–S89", 30, "Связь с нагрузкой/травмой")
        add("Тромбоз глубоких вен (исключить при одностороннем отёке)", "I80", 20 + positives * 10,
            "Односторонний отёк голени + боль в икре")
    else:
        add("Состояние требует очной дифференциации", "R69", 30 + positives * 10,
            "Неспецифическая симптоматика — очный осмотр терапевта")
        if any(_kw_hit(k, tn) for k in ["температура", "лихорадка"]):
            add("Острая респираторная инфекция", "J06", 35, "Лихорадка + катаральные симптомы")
        if bmi >= 30:
            add("Ожирение", "E66", 40, f"ИМТ {bmi}")

    # Сортируем по вероятности и отдаём топ-3
    cands.sort(key=lambda c: c.probability, reverse=True)
    # Нормировка не требуется — это независимые оценки; просто ограничиваем топ-3
    return cands[:3]

def _build_diet(
    zone: str, t: str, probable: List[ProbableCondition], requested: bool, bmi: float, lang: str = "ru"
) -> DietInfo:
    l = _norm_lang(lang)
    tn = _normalize_med_text(t)
    # Жёсткий запрет при подозрении на хирургию / кровотечение
    if _surgery_suspected(zone, t, probable):
        if l == "en":
            return DietInfo(
                allowed=False,
                regime="STRICT FASTING: eat and drink nothing until surgeon exam",
                reason="Suspected acute surgical pathology (appendicitis/obstruction/bleeding). Food and water raise peritonitis and aspiration risk.",
                forbidden=["Any food", "Water and drinks", "Laxatives and painkillers without prescription", "Heating pad on abdomen"],
                warning="DO NOT EAT or DRINK. Do not take analgesics — they mask the picture. Call emergency.",
            )
        if l == "kz":
            return DietInfo(
                allowed=False,
                regime="ҚАТАҢ АШТЫҚ: хирург қарауына дейін ештеңе жеуге және ішуге болмайды",
                reason="Жедел хирургиялық патология күдігі (аппендицит/өтімсіздік/қан кету). Тағам мен су перитонит және аспирация қаупін арттырады.",
                forbidden=["Кез келген тағам", "Су және сусындар", "Тағайындаусыз іш жүргізетін және ауырсынуды басатын дәрілер", "Ішке жылытқыш"],
                warning="ЖЕМЕҢІЗ және ІШПЕҢІЗ. Ауырсынуды басатын дәрі ішпеңіз — көріністі бұзады. 103 шақырыңыз.",
            )
        return DietInfo(
            allowed=False,
            regime="СТРОГИЙ ГОЛОД: ничего не есть и не пить до осмотра хирурга",
            reason="Подозрение на острую хирургическую патологию (аппендицит/непроходимость/кровотечение). Еда и вода повышают риск перитонита и аспирации при экстренной операции.",
            forbidden=["Любая еда", "Вода и напитки", "Слабительные и обезболивающие без назначения", "Грелка на живот"],
            warning="НЕ ЕШЬТЕ и НЕ ПЕЙТЕ. Не принимайте анальгетики/спазмолитики — они стирают картину. Вызовите 103.",
        )

    if _gi_diabetes_obesity_context(t, probable, bmi) or requested:
        diabetes = any("E11" in p.icd10 for p in probable) or any(_kw_hit(k, tn) for k in ["диабет", "diabetes", "қант"])
        if diabetes:
            if l == "en":
                return DietInfo(
                    allowed=True,
                    regime="Table No.9 (glycemic control): 3 main meals + 1–2 snacks, no sugar",
                    reason="Suspected glycemia/diabetes or direct request. Confirm with blood glucose.",
                    recommended=["Vegetables 400–500 g/day", "Whole grains instead of white bread",
                                 "Lean protein: chicken, fish, legumes", "Sugar-free dairy", "Water instead of juices/soda"],
                    forbidden=["Sugar, honey, sweets", "White bread and pastries", "Sweet drinks and juices", "Alcohol", "Fast food and trans fats"],
                    menu_example=["Breakfast: oatmeal + egg + vegetables",
                                  "Lunch: vegetable soup + chicken/fish + buckwheat",
                                  "Snack: sugar-free yogurt + nuts 20–30 g",
                                  "Dinner: fish + steamed vegetables"],
                )
            if l == "kz":
                return DietInfo(
                    allowed=True,
                    regime="№9 үстел (гликемияны бақылау): 3 негізгі ас + 1–2 тіскебасар, қантсыз",
                    reason="Гликемия/диабет күдігі немесе тікелей сұраныс. Қан глюкозасымен растау қажет.",
                    recommended=["Көкөніс 400–500 г/тәул", "Ақ нан орнына дәнді дақылдар",
                                 "Майсыз ақуыз: тауық, балық, бұршақ", "Қантсыз сүт өнімдері", "Шырын/газды су орнына су"],
                    forbidden=["Қант, бал, тәттілер", "Ақ нан және бәліш", "Тәтті сусындар мен шырындар", "Алкоголь", "Фастфуд және трансмайлар"],
                    menu_example=["Таңғы ас: сұлы ботқасы + жұмыртқа + көкөніс",
                                  "Түскі ас: көкөніс сорпасы + тауық/балық + қарақұмық",
                                  "Тіскебасар: қантсыз йогурт + жаңғақ 20–30 г",
                                  "Кешкі ас: балық + буға піскен көкөніс"],
                )
            return DietInfo(
                allowed=True,
                regime="Стол №9 (щадящий, контроль гликемии): 3 основных приёма + 1–2 перекуса, без сахара",
                reason="Подозрение на нарушение гликемии / диабет либо прямой запрос. Требуется подтверждение глюкозой крови.",
                recommended=["Овощи 400–500 г/сут", "Цельнозерновые вместо белого хлеба", "Нежирный белок: курица, рыба, бобовые",
                             "Кисломолочные без сахара", "Вода вместо соков/газировки"],
                forbidden=["Сахар, мёд, сладости", "Белый хлеб и выпечка", "Сладкие напитки и соки", "Алкоголь", "Фастфуд и трансжиры"],
                menu_example=["Завтрак: овсянка на воде + яйцо + овощи",
                              "Обед: суп овощной + курица/рыба + гречка",
                              "Перекус: йогурт без сахара + орехи 20–30 г",
                              "Ужин: рыба + овощи на пару"],
            )
        if l == "en":
            return DietInfo(
                allowed=True,
                regime="Gentle diet (tables No.1/2/4 as tolerated): 4–5 small warm meals",
                reason="GI symptoms or abnormal BMI / direct user request.",
                recommended=["Porridge with water (rice, oatmeal)", "Pureed soups", "Boiled/steamed lean meat and fish",
                             "Baked vegetables", "Water 1.5–2 L/day (unless restricted)"],
                forbidden=["Fatty, fried, smoked", "Spicy and marinades", "Alcohol", "Coffee on empty stomach", "Fresh pastries, legumes if bloated"],
                menu_example=["Breakfast: rice porridge + banana",
                              "Lunch: zucchini puree soup + turkey + potato",
                              "Snack: baked apple",
                              "Dinner: steamed fish + carrot/zucchini"],
            )
        if l == "kz":
            return DietInfo(
                allowed=True,
                regime="Жұмсақ диета (№1/2/4 үстелдер типі): күніне 4–5 рет жылы жұмсақ тағам",
                reason="Гастроэнтерологиялық симптомдар немесе ДСИ нормадан тыс / тікелей сұраныс.",
                recommended=["Судағы ботқалар (күріш, сұлы)", "Езбе сорпалар", "Қайнатылған/буға піскен майсыз ет пен балық",
                             "Пештегі көкөністер", "Су 1.5–2 л/тәул (шектеу болмаса)"],
                forbidden=["Майlı, қуырылған, ысталған", "Ащы және маринадтар", "Алкоголь", "Ашқарынға кофе", "Жаңа бәліш, кепкенде бұршақ"],
                menu_example=["Таңғы ас: күріш ботқасы + банан",
                              "Түскі ас: кәді езбе сорпасы + күркетауық + картоп",
                              "Тіскебасар: пештегі алма",
                              "Кешкі ас: буға піскен балық + сәбіз/кәді"],
            )
        return DietInfo(
            allowed=True,
            regime="Щадящая диета (по типу столов №1/2/4 по переносимости): дробно 4–5 раз, тёплая мягкая пища",
            reason="Гастроэнтерологическая симптоматика или ИМТ вне нормы / прямой запрос пользователя.",
            recommended=["Каши на воде (рис, овсянка)", "Супы-пюре", "Отварное/паровое нежирное мясо и рыба",
                         "Печёные овощи", "Вода 1.5–2 л/сут (если нет ограничений кардиолога/нефролога)"],
            forbidden=["Жирное, жареное, копчёное", "Острое и маринады", "Алкоголь", "Кофе натощак", "Свежая выпечка, бобовые при вздутии"],
            menu_example=["Завтрак: рисовая каша + банан",
                          "Обед: суп-пюре из кабачка + индейка + картофель",
                          "Полдник: печёное яблоко",
                          "Ужин: рыба на пару + морковь/кабачок"],
        )

    if l == "en":
        return DietInfo(
            allowed=False,
            regime="No special therapeutic diet indicated",
            reason="No GI/metabolic indications and no direct diet request. Regular balanced nutrition is enough.",
            recommended=["Vegetables and fruits daily", "Enough protein", "Water as desired"],
            forbidden=[],
        )
    if l == "kz":
        return DietInfo(
            allowed=False,
            regime="Арнайы емдік диета көрсетілмеген",
            reason="Гастроэнтерологиялық/метаболикалық көрсеткіштер жоқ және диетаға тікелей сұраныс болмады. Кәдімгі теңгерімді тамақтану жеткілікті.",
            recommended=["Күнде көкөніс пен жеміс", "Жеткілікті ақуыз", "Шөлге қарай су"],
            forbidden=[],
        )
    return DietInfo(
        allowed=False,
        regime="Специальная лечебная диета не показана",
        reason="Гастроэнтерологических/метаболических показаний нет и прямого запроса на диету не было. Достаточно обычного сбалансированного питания.",
        recommended=["Овощи и фрукты ежедневно", "Достаточный белок", "Вода по жажде"],
        forbidden=[],
    )

def _build_actions(
    level: str, zone: str, probable: List[ProbableCondition], t: str, lang: str = "ru"
) -> Tuple[List[str], str, bool, List[str]]:
    l = _norm_lang(lang)
    top = probable[0] if probable else None
    if l == "en":
        doctor_map = {
            "chest": "cardiologist (or emergency for acute pain, then cardiologist)",
            "abdomen": "surgeon in person for acute pain / gastroenterologist for chronic",
            "head": "neurologist (or emergency for FAST signs)",
            "skin": "dermatologist (or surgeon if spreading/pus)",
            "limb": "traumatologist/neurologist",
            "general": "GP / therapist",
        }
    elif l == "kz":
        doctor_map = {
            "chest": "кардиолог (жедел ауырсынуда — жедел жәрдем, содан кейін кардиолог)",
            "abdomen": "жедел ауырсынуда хирург / созылмалыда гастроэнтеролог",
            "head": "невролог (FAST белгілерінде — жедел жәрдем)",
            "skin": "дерматолог (жайылса/іріңде — хирург)",
            "limb": "травматолог/невролог",
            "general": "терапевт",
        }
    else:
        doctor_map = {
            "chest": "кардиолог (а при острой боли — скорая, затем кардиолог)",
            "abdomen": "хирург очно при острой боли / гастроэнтеролог при хронической",
            "head": "невролог (а при FAST-признаках — скорая)",
            "skin": "дерматолог (а при быстром распространении/гное — хирург)",
            "limb": "травматолог/невролог",
            "general": "терапевт",
        }
    see_doctor = doctor_map.get(zone, doctor_map["general"])
    emergency = level in ("ORANGE", "RED")

    actions: List[str] = []
    if l == "en":
        if level == "RED":
            actions += [
                "1. Call emergency NOW — 103 (or 112). Do not drive yourself.",
                "2. Rest, fresh air; sit/lie down, loosen clothing.",
                "3. For chest pain: chew aspirin 150–300 mg ONLY if no allergy/bleeding and dispatcher approves.",
                "4. Note onset time and all drugs taken — hand to the crew.",
                f"5. After stabilization — urgently to: {see_doctor}.",
            ]
        elif level == "ORANGE":
            actions += [
                "1. In-person exam within hours; if worse — emergency.",
                "2. Measure temperature, BP, pulse; track dynamics.",
                "3. Take documents, drug and allergy list.",
                f"4. Specialist: {see_doctor}.",
            ]
        elif level == "YELLOW":
            actions += [
                "1. Routine visit within 1–3 days.",
                "2. Keep a symptom diary 48–72 h (what/when/triggers).",
                f"3. Specialist: {see_doctor}.",
            ]
        else:
            actions += [
                "1. No acute emergency indications — observe 24–48 h.",
                "2. If worse/new symptoms — repeat screening or see a doctor.",
                f"3. For prevention — {see_doctor}, routine.",
            ]
        if top:
            band = likelihood_label(top.probability, "en")
            actions.append(f"Possible cause to discuss with a doctor (not a diagnosis), likelihood: {band} — {top.name} ({top.icd10}).")
        forbidden = [
            "Do not self-medicate with antibiotics or hormones.",
            "Do not apply a heating pad to acute abdominal pain.",
            "Do not open abscesses at home.",
            "Do not delay emergency for life-threats (chest pain >15 min, FAST, bleeding, anaphylaxis).",
        ]
        if _surgery_suspected(zone, t, probable):
            forbidden.insert(0, "Strictly DO NOT eat or drink before surgeon exam; no painkillers.")
        return actions, see_doctor, emergency, forbidden
    if l == "kz":
        if level == "RED":
            actions += [
                "1. ШҰҒЫЛ жедел жәрдем шақырыңыз — 103 (немесе 112). Өзіңіз көлік жүргізбеңіз.",
                "2. Тыныштық, таза ауа; отырыңыз/жатыңыз, киімді босатыңыз.",
                "3. Кеуде ауырсынуында: аспирин 150–300 мг тек аллергия/қан кету жоқ болса және диспетчер рұқсат етсе.",
                "4. Басталу уақытын және ішкен дәрілерді жазыңыз — бригадаға беріңіз.",
                f"5. Тұрақтанған соң — шұғыл: {see_doctor}.",
            ]
        elif level == "ORANGE":
            actions += [
                "1. Алдағы сағаттарда дәрігерге көрініңіз; нашарласа — 103.",
                "2. Температура, АҚ, пульс өлшеңіз; динамиканы бақылаңыз.",
                "3. Құжаттар, дәрі мен аллергия тізімін алыңыз.",
                f"4. Бейінді дәрігер: {see_doctor}.",
            ]
        elif level == "YELLOW":
            actions += [
                "1. 1–3 күнде жоспарлы дәрігерге барыңыз.",
                "2. 48–72 сағ симптом күнделігін жүргізіңіз.",
                f"3. Бейінді дәрігер: {see_doctor}.",
            ]
        else:
            actions += [
                "1. Жедел шұғыл көрсеткіш жоқ — 24–48 сағ бақылаңыз.",
                "2. Күшейсе/жаңа симптом шықса — қайта скрининг немесе дәрігер.",
                f"3. Алдын алу үшін — {see_doctor}, жоспарлы.",
            ]
        if top:
            band = likelihood_label(top.probability, "kz")
            actions.append(f"Дәрігермен талқыланатын мүмкін себеп (диагноз емес, бетпе-бет қаралу қажет), ықтималдығы: {band} — {top.name} ({top.icd10}).")
        forbidden = [
            "Антибиотик пен гормонмен өздігінен емделмеңіз.",
            "Жедел іш ауырсынуында жылытқыш баспаңыз.",
            "Іріңдікті үйде ашпаңыз.",
            "Өмірге қауіпті белгілерде 103 шақыруды кешіктірмеңіз.",
        ]
        if _surgery_suspected(zone, t, probable):
            forbidden.insert(0, "Хирург қарауына дейін ішіп-жеуге ҚАТАҢ тыйым; ауырсынуды басатын дәрі ішпеңіз.")
        return actions, see_doctor, emergency, forbidden

    # ru
    actions = []
    if level == "RED":
        actions += [
            "1. НЕМЕДЛЕННО вызовите скорую — 103 (или 112). Не садитесь за руль сами.",
            "2. Обеспечьте покой, доступ воздуха; сядьте/лягте, ослабьте одежду.",
            "3. При боли в груди: разжевать аспирин 150–300 мг ТОЛЬКО если нет аллергии/кровотечения и скорая одобрила по телефону.",
            "4. Запишите время начала симптомов и все принятые препараты — передайте бригаде.",
            f"5. После стабилизации — срочно к врачу: {see_doctor}.",
        ]
    elif level == "ORANGE":
        actions += [
            "1. В ближайшие часы — очный осмотр врача; при ухудшении — 103.",
            "2. Измерьте температуру, АД, пульс; зафиксируйте динамику симптомов.",
            "3. Возьмите документы, список лекарств и аллергий.",
            f"4. Профильный врач: {see_doctor}.",
        ]
    elif level == "YELLOW":
        actions += [
            "1. В ближайшие 1–3 дня — плановый визит к врачу.",
            "2. Ведите дневник симптомов 48–72 часа (что/когда/провоцирует).",
            f"3. Профильный врач: {see_doctor}.",
        ]
    else:
        actions += [
            "1. Острых показаний к экстренной помощи нет — наблюдайте 24–48 часов.",
            "2. При усилении/новых симптомах — повторный скрининг или визит к врачу.",
            f"3. Для профилактики — {see_doctor} планово.",
        ]

    if top:
        band = likelihood_label(top.probability, "ru")
        actions.append(f"Возможные причины для обсуждения с врачом (не диагноз, требуется очно): {top.name} ({top.icd10}), вероятность: {band}.")

    forbidden = [
        "Не занимайтесь самолечением антибиотиками и гормонами без назначения.",
        "Не прикладывайте грелку к животу при острой боли.",
        "Не вскрывайте гнойники дома.",
        "Не откладывайте вызов 103 при жизнеугрожающих признаках (боль в груди >15 мин, FAST, кровотечение, анафилаксия).",
    ]
    if _surgery_suspected(zone, t, probable):
        forbidden.insert(0, "Категорически НЕ есть и НЕ пить до осмотра хирурга; не принимать обезболивающие.")

    return actions, see_doctor, emergency, forbidden

def _build_evidence(zone: str, probable: List[ProbableCondition], lang: str = "ru") -> List[EvidenceSource]:
    l = _norm_lang(lang)
    who_title = {"ru": "ВОЗ — рекомендации по первичной помощи", "en": "WHO — primary care recommendations", "kz": "ДДҰ — алғашқы көмек ұсынымдары"}[l]
    heart_title = {"ru": "PubMed — HEART score для боли в груди (ID: 32979527)", "en": "PubMed — HEART score for chest pain (ID: 32979527)", "kz": "PubMed — кеуде ауырсынуына HEART шкаласы (ID: 32979527)"}[l]
    base: List[EvidenceSource] = [
        EvidenceSource(title=who_title,
                       url="https://www.who.int/publications", type="WHO"),
        EvidenceSource(title=heart_title,
                       url="https://pubmed.ncbi.nlm.nih.gov/32979527/", type="PubMed"),
    ]
    zone_evidence = {
        "chest": EvidenceSource(
            title="ESC Guidelines — острый коронарный синдром без подъёма ST",
            url="https://www.escardio.org/Guidelines", type="Protocol"),
        "abdomen": EvidenceSource(
            title="WSES Guidelines — острый аппендицит (PMID: 34605800)",
            url="https://pubmed.ncbi.nlm.nih.gov/34605800/", type="Protocol"),
        "head": EvidenceSource(
            title="AHA/ASA Guidelines — раннее ведение острого ишемического инсульта",
            url="https://www.ahajournals.org/doi/10.1161/STR.0000000000000211", type="Protocol"),
        "skin": EvidenceSource(
            title="IDSA Guidelines — инфекции кожи и мягких тканей (PMID: 24947530)",
            url="https://pubmed.ncbi.nlm.nih.gov/24947530/", type="Protocol"),
        "limb": EvidenceSource(
            title="NICE NG89 — венозная тромбоэмболия: диагностика и ведение",
            url="https://www.nice.org.uk/guidance/ng89", type="Protocol"),
        "general": EvidenceSource(
            title="PubMed — qSOFA/сепсис-скрининг (ID: 27014596)",
            url="https://pubmed.ncbi.nlm.nih.gov/27014596/", type="PubMed"),
    }
    specific = zone_evidence.get(zone)
    out = [base[0]]
    if specific:
        out.append(specific)
    out.append(base[1])
    return out[:3]
