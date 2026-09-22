"""Клиническая логика триажа MediAI: вопросы, BMI, риски, диета, действия."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .schemas import (
    ConditionItem,
    DietInfo,
    EvidenceSource,
    ProbableCondition,
    TriageFinalRequest,
    TriageInitialRequest,
    TriageQuestion,
)

# ---------------------------------------------------------------------------
# Каталог заболеваний для мега-меню (с кодами МКБ-10)
# ---------------------------------------------------------------------------

CONDITIONS_CATALOG: Dict[str, List[ConditionItem]] = {
    "кардиология": [
        ConditionItem(name="Стенокардия", icd10="I20", category="кардиология",
                      urgency_hint="Загрудинная давящая боль — исключить ОКС, вызвать 103"),
        ConditionItem(name="Острый инфаркт миокарда", icd10="I21", category="кардиология",
                      urgency_hint="RED: жгучая боль >15 мин, одышка, холодный пот — срочно 103"),
        ConditionItem(name="Эссенциальная гипертензия", icd10="I10", category="кардиология",
                      urgency_hint="АД ≥140/90 повторно — терапевт/кардиолог планово"),
        ConditionItem(name="Фибрилляция предсердий", icd10="I48", category="кардиология",
                      urgency_hint="Перебои ритма, одышка — кардиолог, ЭКГ"),
    ],
    "гастроэнтерология": [
        ConditionItem(name="Гастроэзофагеальная рефлюксная болезнь", icd10="K21",
                      category="гастроэнтерология", urgency_hint="Изжога — гастроэнтеролог"),
        ConditionItem(name="Язва желудка", icd10="K25", category="гастроэнтерология",
                      urgency_hint="Голодные/ночные боли, черный стул — срочно к врачу"),
        ConditionItem(name="Гастрит", icd10="K29", category="гастроэнтерология",
                      urgency_hint="Диета №1/2, гастроэнтеролог"),
        ConditionItem(name="Синдром раздражённого кишечника", icd10="K59",
                      category="гастроэнтерология", urgency_hint="Гастроэнтеролог, FODMAP-протокол"),
        ConditionItem(name="Сахарный диабет 2 типа", icd10="E11",
                      category="гастроэнтерология", urgency_hint="Жажда, частое мочеиспускание — глюкоза, эндокринолог"),
        ConditionItem(name="Ожирение", icd10="E66",
                      category="гастроэнтерология", urgency_hint="ИМТ ≥30 — эндокринолог, диета, активность"),
    ],
    "неврология": [
        ConditionItem(name="Мигрень", icd10="G43", category="неврология",
                      urgency_hint="Пульсирующая односторонняя боль с аурой — невролог"),
        ConditionItem(name="Головная боль напряжения", icd10="G44.2", category="неврология",
                      urgency_hint="Давящая двусторонняя — невролог/терапевт"),
        ConditionItem(name="Инсульт (подозрение)", icd10="I63/I64", category="неврология",
                      urgency_hint="RED: FAST — асимметрия лица, слабость руки, речь — срочно 103"),
        ConditionItem(name="Дорсопатия / боль в спине", icd10="M54", category="неврология",
                      urgency_hint="Невролог; красные флаги: онемение промежности, задержка мочи — 103"),
    ],
    "дерматология": [
        ConditionItem(name="Атопический дерматит", icd10="L20", category="дерматология",
                      urgency_hint="Дерматолог, эмоленты"),
        ConditionItem(name="Псориаз", icd10="L40", category="дерматология",
                      urgency_hint="Дерматолог планово"),
        ConditionItem(name="Целлюлит / рожа", icd10="L03", category="дерматология",
                      urgency_hint="Быстрое распространение + лихорадка — хирург/инфекционист срочно"),
        ConditionItem(name="Абсцесс кожи", icd10="L02", category="дерматология",
                      urgency_hint="Гнойник, флюктуация — хирург, не вскрывать дома"),
    ],
    "хирургия": [
        ConditionItem(name="Острый аппендицит", icd10="K35", category="хирургия",
                      urgency_hint="RED: миграция боли в правую подвздошную область + лихорадка — 103, голод"),
        ConditionItem(name="Желчнокаменная болезнь / колика", icd10="K80", category="хирургия",
                      urgency_hint="Боль в правом подреберье после жирного — хирург, УЗИ"),
        ConditionItem(name="Паховая грыжа", icd10="K40", category="хирургия",
                      urgency_hint="Выпячивание, невправимость + боль — 103 (ущемление)"),
        ConditionItem(name="Кишечная непроходимость (подозрение)", icd10="K56",
                      category="хирургия", urgency_hint="RED: вздутие, нет стула/газов, рвота — 103, голод"),
    ],
}


def get_conditions_catalog() -> Dict[str, List[ConditionItem]]:
    return CONDITIONS_CATALOG


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def calc_bmi(weight_kg: float, height_cm: float) -> float:
    h_m = max(height_cm / 100.0, 0.5)
    return round(weight_kg / (h_m ** 2), 1)


def bmi_category(bmi: float) -> str:
    if bmi < 18.5:
        return "Дефицит массы тела"
    if bmi < 25:
        return "Норма"
    if bmi < 30:
        return "Избыточная масса тела"
    if bmi < 35:
        return "Ожирение I степени"
    if bmi < 40:
        return "Ожирение II степени"
    return "Ожирение III степени"


def _text(req: TriageInitialRequest | TriageFinalRequest) -> str:
    parts = [req.body_zone or "", req.symptoms_text or "", " ".join(req.tags or [])]
    return " ".join(parts).lower()


def normalize_zone(body_zone: str) -> str:
    z = (body_zone or "").strip().lower()
    chest_keys = ["chest", "груд", "сердц", "thorax", "кардио"]
    abdomen_keys = ["abdomen", "живот", "абдомин", "брюш", "подвздош", "эпигастр", "жкт", "кишеч", "желуд"]
    head_keys = ["head", "голов", "невро", "мозг", "шея", "neuro", "мигрень"]
    skin_keys = ["skin", "кожа", "дерм", "сыпь", "прыщ", "зуд", "дермат"]
    limb_keys = ["limb", "нога", "рука", "конечн", "спина", "поясниц", "сустав", "колен"]
    for key in chest_keys:
        if key in z:
            return "chest"
    for key in abdomen_keys:
        if key in z:
            return "abdomen"
    for key in head_keys:
        if key in z:
            return "head"
    for key in skin_keys:
        if key in z:
            return "skin"
    for key in limb_keys:
        if key in z:
            return "limb"
    return "general"


def triage_level_from_score(score: float) -> str:
    if score <= 25:
        return "GREEN"
    if score <= 60:
        return "YELLOW"
    if score <= 85:
        return "ORANGE"
    return "RED"


# ---------------------------------------------------------------------------
# Первичный скрининг: ровно 3 уточняющих вопроса
# ---------------------------------------------------------------------------

_QUESTION_BANK: Dict[str, List[Tuple[str, str, str]]] = {
    "chest": [
        ("chest_pressing", "Боль за грудиной давящая, сжимающая или жгучая, длится более 5–15 минут?",
         "Исключение острого коронарного синдрома (I20–I21)"),
        ("chest_breath", "Есть ли одышка, нехватка воздуха, холодный пот, тошнота или страх смерти на фоне боли?",
         "Скрининг инфаркта / ТЭЛА / пневмоторакса"),
        ("chest_radiation", "Отдаёт ли боль в левую руку, плечо, шею, нижнюю челюсть или спину?",
         "Иррадиация — типичный признак кардиальной боли"),
    ],
    "abdomen": [
        ("abd_migration", "Боль переместилась и сейчас сосредоточена внизу живота справа, усиливается при ходьбе/кашле?",
         "Исключение острого аппендицита (K35)"),
        ("abd_fever_vomit", "Есть ли повышение температуры ≥37.5°C, тошнота или рвота?",
         "Системные признаки острой хирургической патологии"),
        ("abd_tension", "Стал ли живот твёрдым, резко болезненным при нажатии, есть ли вздутие и задержка стула/газов?",
         "Исключение перитонита / непроходимости (K56)"),
    ],
    "head": [
        ("neuro_fast", "Есть ли ВНЕЗАПНО: перекос лица, слабость/онемение руки или ноги с одной стороны, нарушение речи?",
         "FAST-скрининг инсульта (I63/I64)"),
        ("neuro_thunder", "Боль началась внезапно как «удар грома» — самая сильная в жизни, с рвотой, потерей сознания или двоением?",
         "Исключение субарахноидального кровоизлияния / гипертонического криза"),
        ("neuro_fever_neck", "Есть ли высокая температура, ригидность затылка (невозможно прижать подбородок к груди), сыпь?",
         "Исключение менингита/энцефалита"),
    ],
    "skin": [
        ("skin_spread", "Покраснение/отёк быстро распространяется (заметно за часы), полоса идёт по коже, боль усиливается?",
         "Исключение целлюлита/рожи (L03) — риск сепсиса"),
        ("skin_fever_pus", "Есть ли лихорадка ≥38°C, гной, вскрывшийся пузырёк, чёрная корка или сильная болезненность?",
         "Признаки бактериальной инфекции / абсцесса (L02)"),
        ("skin_breath_allergy", "Есть ли отёк губ/языка, затруднение дыхания, сыпь по всему телу после лекарства/еды/укуса?",
         "Исключение анафилаксии — состояние RED"),
    ],
    "limb": [
        ("limb_trauma", "Была ли травма/падение, слышен ли хруст, можете ли опираться на конечность?",
         "Исключение перелома/вывиха"),
        ("limb_neuro", "Есть ли онемение, «мурашки», слабость стопы/кисти, проблемы с мочеиспусканием или онемение промежности?",
         "Красные флаги сдавления нервного корешка / синдрома конского хвоста"),
        ("limb_swelling", "Есть ли резкий односторонний отёк голени, покраснение и боль в икре, одышка или боль в груди?",
         "Исключение тромбоза глубоких вен / ТЭЛА"),
    ],
    "general": [
        ("gen_red_acute", "Есть ли СЕЙЧАС: сильная боль в груди, удушье, обморок, судороги, рвота «кофейной гущей» или чёрный стул?",
         "Универсальный скрининг жизнеугрожающих состояний"),
        ("gen_fever", "Есть ли температура ≥38.5°C, озноб, спутанность сознания или резкая слабость?",
         "Скрининг сепсиса/тяжёлой инфекции"),
        ("gen_dynamic", "Симптомы резко усилились за последние часы, появилась новая сильная боль, онемение или нарушение речи/зрения?",
         "Оценка динамики — маркер ORANGE/RED"),
    ],
}


def generate_initial_questions(req: TriageInitialRequest) -> List[TriageQuestion]:
    """Вернуть ровно 3 клинических уточняющих вопроса."""
    zone = normalize_zone(req.body_zone)
    # Эвристика: если текст явно указывает на другую зону — корректируем.
    t = _text(req)
    if any(k in t for k in ["аппендицит", "справа внизу живота", "подвздош"]) and zone != "abdomen":
        zone = "abdomen"
    if any(k in t for k in ["грудин", "за грудиной", "отдаёт в руку", "жмет в груди"]) and zone != "chest":
        zone = "chest"
    if any(k in t for k in ["перекос лица", "онемела рука", "нарушение речи", "инсульт"]) and zone != "head":
        zone = "head"

    bank = _QUESTION_BANK.get(zone, _QUESTION_BANK["general"])
    return [
        TriageQuestion(id=qid, text=text, reason=reason)
        for (qid, text, reason) in bank[:3]
    ]


# ---------------------------------------------------------------------------
# Финальная оценка
# ---------------------------------------------------------------------------

_RED_PHRASES = ["да", "yes", "есть", "сильная", "резко", "внезапно", "не могу", "невозможно"]


def _answer_is_positive(answer: str) -> bool:
    a = (answer or "").strip().lower()
    if a in ("да", "yes", "есть", "имеется", "наблюдается"):
        return True
    # «да, ...» тоже считаем положительным
    if a.startswith("да") or a.startswith("yes"):
        return True
    return False


def _keyword_score(t: str) -> Tuple[float, List[str]]:
    """Эвристический скоринг по свободному тексту. Возвращает (баллы, флаги)."""
    score = 0.0
    flags: List[str] = []
    red_groups = [
        (["боль за грудиной", "давит в груди", "жжет в груди", "отдаёт в руку", "холодный пот", "удушье", "нехватка воздуха"], 38, "кардиальный красный флаг"),
        (["перекос лица", "онемела рука", "нарушение речи", "инсульт", "fast"], 42, "неврологический красный флаг (FAST)"),
        (["рвота кофейной", "черный стул", "мелена", "кровь в стуле", "кровотечение"], 40, "кровотечение ЖКТ"),
        (["острая боль справа внизу", "миграция боли", "твёрдый живот", "твердый живот", "доскообразный", "нет стула и газов", "задержка стула"], 36, "острая хирургическая патология"),
        (["анафилакси", "отёк губ", "отек губ", "отёк языка", "задыхаюсь"], 45, "анафилаксия"),
        (["температура 39", "температура 40", "38.5", "39", "озноб", "спутанность", "потеря сознания", "обморок", "судороги"], 25, "системная тяжесть"),
        (["тошнота", "рвота", "лихорадка", "температура"], 10, "системные симптомы"),
    ]
    for keywords, pts, flag in red_groups:
        if any(k in t for k in keywords):
            score += pts
            flags.append(flag)
    # Возраст и хронические маркеры
    if any(k in t for k in ["диабет", "давление", "гипертония", "астма", "ибс", "инфаркт в прошлом"]):
        score += 6
        flags.append("отягощённый анамнез")
    return score, flags


def evaluate_final(req: TriageFinalRequest) -> dict:
    t = _text(req)
    zone = normalize_zone(req.body_zone)
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    bmi_cat = bmi_category(bmi)

    # --- базовый скоринг ---
    score = 0.0
    reasons: List[str] = []

    kw_score, kw_flags = _keyword_score(t)
    score += kw_score
    reasons.extend(kw_flags)

    # Ответы на 3 вопроса: каждый «Да» сильно повышает риск.
    positives = sum(1 for a in req.answers if _answer_is_positive(a.answer))
    # Вес зависит от зоны: для груди/головы/живота выше.
    weight_map = {"chest": 18, "head": 18, "abdomen": 16, "skin": 12, "limb": 12, "general": 14}
    w = weight_map.get(zone, 14)
    if positives:
        score += positives * w
        reasons.append(f"положительных ответов на уточняющие вопросы: {positives}/3")

    # Возраст
    if req.age >= 65:
        score += 10
        reasons.append("возраст ≥65")
    elif req.age >= 50:
        score += 5

    # ИМТ
    if bmi >= 30:
        score += 8
        reasons.append(f"ИМТ {bmi} (ожирение)")
    elif bmi >= 25:
        score += 3

    # Неопределённость («не уверен») — небольшой плюс к осторожности
    unsure = sum(1 for a in req.answers if "не уверен" in (a.answer or "").lower() or "не знаю" in (a.answer or "").lower())
    score += unsure * 4

    score = max(0.0, min(100.0, round(score, 1)))
    level = triage_level_from_score(score)

    probable = _build_probable_conditions(zone, t, req, positives, bmi)
    diet = _build_diet(zone, t, probable, req.request_diet, bmi)
    actions, see_doctor, emergency_call, forbidden = _build_actions(level, zone, probable, t)
    evidence = _build_evidence(zone, probable)

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
    }


def _build_probable_conditions(
    zone: str, t: str, req: TriageFinalRequest, positives: int, bmi: float
) -> List[ProbableCondition]:
    cands: List[ProbableCondition] = []

    def add(name: str, icd10: str, prob: float, reason: str) -> None:
        cands.append(ProbableCondition(
            name=name, icd10=icd10,
            probability=float(max(5.0, min(95.0, round(prob, 1)))),
            reason=reason,
        ))

    if zone == "chest":
        base = 20 + positives * 15
        add("Острый коронарный синдром (стенокардия / инфаркт)", "I20–I21", base + 15,
            "Загрудинная боль ± иррадиация/одышка — требует исключения ОКС")
        add("Эссенциальная гипертензия", "I10", 30 + positives * 5, "Связанная кардиальная симптоматика")
        add("Гастроэзофагеальный рефлюкс (кардиалгия-имитация)", "K21", 25, "Жжение за грудиной может имитировать кардиалгию")
    elif zone == "abdomen":
        surg_hint = any(k in t for k in ["справа внизу", "миграция", "подвздош", "аппендицит", "твёрдый", "твердый"])
        base = 20 + positives * 14
        if surg_hint or positives >= 2:
            add("Острый аппендицит (подозрение)", "K35", base + 15, "Миграция боли вправо + лихорадка/тошнота")
            add("Желчнокаменная болезнь / колика", "K80", base, "Боль в животе, связь с жирной пищей")
        else:
            add("Острый гастрит", "K29", base + 10, "Боль/дискомфорт в эпигастрии")
            add("Язвенная болезнь желудка", "K25", base, "Голодные/ночные боли — исключить осложнение")
        add("Синдром раздражённого кишечника", "K59", 25, "Функциональный дифференциальный диагноз")
        if bmi >= 30 or "диабет" in t or "жажда" in t:
            add("Сахарный диабет 2 типа (скрининг)", "E11", 30, "Ожирение/жажда — проверить глюкозу")
    elif zone == "head":
        fast_hint = any(k in t for k in ["перекос", "онемела", "речь", "инсульт", "слабость руки"])
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
        if "температура" in t or "лихорадка" in t:
            add("Острая респираторная инфекция", "J06", 35, "Лихорадка + катаральные симптомы")
        if bmi >= 30:
            add("Ожирение", "E66", 40, f"ИМТ {bmi}")

    # Сортируем по вероятности и отдаём топ-3
    cands.sort(key=lambda c: c.probability, reverse=True)
    # Нормировка не требуется — это независимые оценки; просто ограничиваем топ-3
    return cands[:3]


def _surgery_suspected(zone: str, t: str, probable: List[ProbableCondition]) -> bool:
    icds = " ".join(p.icd10 for p in probable)
    if zone == "abdomen" and any(k in t for k in
                                 ["аппендицит", "справа внизу", "подвздош", "твёрдый живот",
                                  "твердый живот", "нет стула", "непроходимость", "досkoобразный".replace("k", "к")]):
        return True
    if "K35" in icds or "K56" in icds:
        return True
    if any(k in t for k in ["рвота кофейной", "черный стул", "мелена"]):
        return True
    return False


def _gi_diabetes_obesity_context(t: str, probable: List[ProbableCondition], bmi: float) -> bool:
    icds = " ".join(p.icd10 for p in probable)
    gi_markers = ["K21", "K25", "K29", "K59", "E11", "E66", "K80"]
    if any(m in icds for m in gi_markers):
        return True
    if bmi >= 30:
        return True
    if any(k in t for k in ["изжога", "гастрит", "язва", "диабет", "жажда", "ожирение", "понос", "запор", "вздутие"]):
        return True
    return False


def _build_diet(
    zone: str, t: str, probable: List[ProbableCondition], requested: bool, bmi: float
) -> DietInfo:
    # Жёсткий запрет при подозрении на хирургию / кровотечение
    if _surgery_suspected(zone, t, probable):
        return DietInfo(
            allowed=False,
            regime="СТРОГИЙ ГОЛОД: ничего не есть и не пить до осмотра хирурга",
            reason="Подозрение на острую хирургическую патологию (аппендицит/непроходимость/кровотечение). Еда и вода повышают риск перитонита и аспирации при экстренной операции.",
            forbidden=["Любая еда", "Вода и напитки", "Слабительные и обезболивающие без назначения", "Грелка на живот"],
            warning="НЕ ЕШЬТЕ и НЕ ПЕЙТЕ. Не принимайте анальгетики/спазмолитики — они стирают картину. Вызовите 103.",
        )

    if _gi_diabetes_obesity_context(t, probable, bmi) or requested:
        diabetes = any("E11" in p.icd10 for p in probable) or "диабет" in t
        if diabetes:
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

    return DietInfo(
        allowed=False,
        regime="Специальная лечебная диета не показана",
        reason="Гастроэнтерологических/метаболических показаний нет и прямого запроса на диету не было. Достаточно обычного сбалансированного питания.",
        recommended=["Овощи и фрукты ежедневно", "Достаточный белок", "Вода по жажде"],
        forbidden=[],
    )


def _build_actions(
    level: str, zone: str, probable: List[ProbableCondition], t: str
) -> Tuple[List[str], str, bool, List[str]]:
    top = probable[0] if probable else None
    doctor_map = {
        "chest": "кардиолог (а при острой боли — скорая, затем кардиолог)",
        "abdomen": "хирург очно при острой боли / гастроэнтеролог при хронической",
        "head": "невролог (а при FAST-признаках — скорая)",
        "skin": "дерматолог (а при быстром распространении/гное — хирург)",
        "limb": "травматолог/невролог",
        "general": "терапевт",
    }
    see_doctor = doctor_map.get(zone, "терапевт")
    emergency = level in ("ORANGE", "RED")

    actions: List[str] = []
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
        actions.append(f"Дифдиагноз для обсуждения с врачом: {top.name} ({top.icd10}), ~{top.probability}%.")

    forbidden = [
        "Не занимайтесь самолечением антибиотиками и гормонами без назначения.",
        "Не прикладывайте грелку к животу при острой боли.",
        "Не вскрывайте гнойники дома.",
        "Не откладывайте вызов 103 при жизнеугрожающих признаках (боль в груди >15 мин, FAST, кровотечение, анафилаксия).",
    ]
    if _surgery_suspected(zone, t, probable):
        forbidden.insert(0, "Категорически НЕ есть и НЕ пить до осмотра хирурга; не принимать обезболивающие.")

    return actions, see_doctor, emergency, forbidden


def _build_evidence(zone: str, probable: List[ProbableCondition]) -> List[EvidenceSource]:
    base: List[EvidenceSource] = [
        EvidenceSource(title="ВОЗ — рекомендации по первичной помощи",
                       url="https://www.who.int/publications", type="WHO"),
        EvidenceSource(title="PubMed — HEART score для боли в груди (ID: 32979527)",
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
