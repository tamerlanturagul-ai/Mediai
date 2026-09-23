"""Single source of truth for i18n (TASK-011 dedup).

- resolve_lang(): the ONE lang fallback (unknown/empty -> "ru").
- normalize_answer(): the ONE RU/EN/KZ answer mapper (yes/no/unsure).
- MESSAGES / LIST_MESSAGES: builder copy tables, selected as
  MESSAGES[key][lang] instead of tripled ``if lang == ...`` branches.
- KW_*: per-lang keyword hint sets (identical content per lang, table form).

Pure code motion: no copy edits, no weight/threshold changes.
"""
from __future__ import annotations

import re

SUPPORTED_LANGS = ("ru", "en", "kz")


def resolve_lang(lang: str | None) -> str:
    """Canonical lang fallback: unknown/empty -> 'ru' (no 422, backward-compatible)."""
    if not isinstance(lang, str):
        return "ru"
    normalized = lang.strip().lower()
    return normalized if normalized in SUPPORTED_LANGS else "ru"


def normalize_answer(answer: str) -> str:
    """Map RU/EN/KZ free-text answer to canonical yes/no/unsure.

    Accepted (case-insensitive):
    - yes: да, yes, иә, есть/имеется/наблюдается, бар/болады (+ "да, ..." / "yes, ..." continuations)
    - no: нет, no, жоқ/жок
    - unsure: не уверен(а)/не знаю, not sure, сенімді емес(пін), unsure
    Ambiguous ("да нет") and other free text raise ValueError (contract: Literal only).
    """
    a = (answer or "").strip().lower()
    if a in ("yes", "no", "unsure"):
        return a
    if any(k in a for k in ("не уверен", "не знаю", "not sure", "сенімді емес", "unsure")):
        return "unsure"
    if a in ("да", "yes", "есть", "имеется", "наблюдается", "иә", "бар", "болады"):
        return "yes"
    # "да, ..." / "yes, ..." continuations are yes, but "да нет" (both markers) is ambiguous -> reject.
    if a.startswith(("да", "yes", "иә")):
        if "нет" in a or re.search(r"\bno\b", a):
            raise ValueError(
                f"Неоднозначный ответ '{answer}': ожидается yes/no/unsure "
                "(или Да/Нет/Не уверен(а), Yes/No/Not sure, Иә/Жоқ/Сенімді емеспін)"
            )
        return "yes"
    if a in ("нет", "no", "жоқ", "жок", "нету"):
        return "no"
    if a.startswith(("нет", "no", "жоқ", "жок")):
        # "no ..." with embedded "yes"/"да" is ambiguous
        if re.search(r"\byes\b", a) or "да" in a:
            raise ValueError(
                f"Неоднозначный ответ '{answer}': ожидается yes/no/unsure "
                "(или Да/Нет/Не уверен(а), Yes/No/Not sure, Иә/Жоқ/Сенімді емеспін)"
            )
        return "no"
    raise ValueError(
        f"Неизвестный ответ '{answer}': ожидается yes/no/unsure "
        "(или Да/Нет/Не уверен(а), Yes/No/Not sure, Иә/Жоқ/Сенімді емеспін)"
    )


# ---------------------------------------------------------------------------
# Builder copy: scalar strings. Placeholders: {bmi}, {see_doctor}, {band}, {name}, {icd}.
# ---------------------------------------------------------------------------

MESSAGES: dict[str, dict[str, str]] = {
    # --- probable conditions: chest ---
    "prob_chest_acs_name": {
        "ru": "Острый коронарный синдром (стенокардия / инфаркт)",
        "en": "Acute coronary syndrome (angina / infarction)",
        "kz": "Жедел коронарлық синдром (стенокардия / инфаркт)",
    },
    "prob_chest_acs_reason": {
        "ru": "Загрудинная боль ± иррадиация/одышка — требует исключения ОКС",
        "en": "Retrosternal pain ± radiation/dyspnea — rule out ACS",
        "kz": "Төс артындағы ауырсыну ± иррадиация/ентігу — ЖҚС жоққа шығару",
    },
    "prob_chest_hyp_name": {
        "ru": "Эссенциальная гипертензия",
        "en": "Essential hypertension",
        "kz": "Эссенциалды гипертензия",
    },
    "prob_chest_hyp_reason": {
        "ru": "Связанная кардиальная симптоматика",
        "en": "Associated cardiac symptoms",
        "kz": "Ілеспе жүрек симптомдары",
    },
    "prob_chest_gerd_name": {
        "ru": "Гастроэзофагеальный рефлюкс (кардиалгия-имитация)",
        "en": "GERD (cardiac mimic)",
        "kz": "ГЭРА (жүрек ауырсынуына ұқсас)",
    },
    "prob_chest_gerd_reason": {
        "ru": "Жжение за грудиной может имитировать кардиалгию",
        "en": "Retrosternal burning may mimic cardiac pain",
        "kz": "Төс артындағы ашу жүрек ауырсынуына ұқсауы мүмкін",
    },
    # --- probable conditions: abdomen ---
    "prob_abd_app_name": {
        "ru": "Острый аппендицит (подозрение)",
        "en": "Acute appendicitis (suspected)",
        "kz": "Жедел аппендицит (күдік)",
    },
    "prob_abd_app_reason": {
        "ru": "Миграция боли вправо + лихорадка/тошнота",
        "en": "Right-sided migration + fever/nausea",
        "kz": "Ауырсынудың оңға ығысуы + қызба/жүрек айну",
    },
    "prob_abd_chole_name": {
        "ru": "Желчнокаменная болезнь / колика",
        "en": "Cholelithiasis / colic",
        "kz": "Өт тас ауруы / шаншу",
    },
    "prob_abd_chole_reason": {
        "ru": "Боль в животе, связь с жирной пищей",
        "en": "Abdominal pain linked to fatty food",
        "kz": "Іш ауырсынуы, майлы тағаммен байланыс",
    },
    "prob_abd_gastr_name": {
        "ru": "Острый гастрит",
        "en": "Acute gastritis",
        "kz": "Жедел гастрит",
    },
    "prob_abd_gastr_reason": {
        "ru": "Боль/дискомфорт в эпигастрии",
        "en": "Epigastric pain/discomfort",
        "kz": "Эпигастрийде ауырсыну/жайсыздық",
    },
    "prob_abd_ulcer_name": {
        "ru": "Язвенная болезнь желудка",
        "en": "Gastric ulcer",
        "kz": "Асқазан жарасы",
    },
    "prob_abd_ulcer_reason": {
        "ru": "Голодные/ночные боли — исключить осложнение",
        "en": "Hunger/night pain — rule out complication",
        "kz": "Аш/түнгі ауырсыну — асқынуды жоққа шығару",
    },
    "prob_abd_ibs_name": {
        "ru": "Синдром раздражённого кишечника",
        "en": "Irritable bowel syndrome",
        "kz": "Тітіркенген ішек синдромы",
    },
    "prob_abd_ibs_reason": {
        "ru": "Функциональный дифференциальный диагноз",
        "en": "Functional differential diagnosis",
        "kz": "Функционалды ажыратпа диагноз",
    },
    "prob_abd_diab_name": {
        "ru": "Сахарный диабет 2 типа (скрининг)",
        "en": "Type 2 diabetes (screening)",
        "kz": "2-типті қант диабеті (скрининг)",
    },
    "prob_abd_diab_reason": {
        "ru": "Ожирение/жажда — проверить глюкозу",
        "en": "Obesity/thirst — check glucose",
        "kz": "Семіздік/шөлдеу — глюкозаны тексеру",
    },
    # --- probable conditions: head ---
    "prob_head_stroke_name": {
        "ru": "Подозрение на инсульт (ТIA/ишемический)",
        "en": "Suspected stroke (TIA/ischemic)",
        "kz": "Инсульт күдігі (ТИА/ишемиялық)",
    },
    "prob_head_stroke_reason": {
        "ru": "FAST-признаки — экстренная помощь",
        "en": "FAST signs — emergency care",
        "kz": "FAST белгілері — шұғыл көмек",
    },
    "prob_head_migr_name": {
        "ru": "Мигрень",
        "en": "Migraine",
        "kz": "Мигрень",
    },
    "prob_head_migr_reason": {
        "ru": "Пульсирующая односторонняя боль ± аура",
        "en": "Pulsating unilateral pain ± aura",
        "kz": "Аурасы бар біржақты солқылдаған ауырсыну",
    },
    "prob_head_tension_name": {
        "ru": "Головная боль напряжения",
        "en": "Tension-type headache",
        "kz": "Кернеулі бас ауруы",
    },
    "prob_head_tension_reason": {
        "ru": "Давящая двусторонняя боль",
        "en": "Pressing bilateral pain",
        "kz": "Қысатын екіжақты ауырсыну",
    },
    # --- probable conditions: skin ---
    "prob_skin_cell_name": {
        "ru": "Целлюлит / рожа (подозрение при быстром распространении)",
        "en": "Cellulitis / erysipelas (if spreading fast)",
        "kz": "Целлюлит / рожа (жылдам жайылса)",
    },
    "prob_skin_cell_reason": {
        "ru": "Быстрое распространение + боль/лихорадка",
        "en": "Rapid spread + pain/fever",
        "kz": "Жылдам жайылу + ауырсыну/қызба",
    },
    "prob_skin_abs_name": {
        "ru": "Абсцесс кожи",
        "en": "Skin abscess",
        "kz": "Тері абсцессі",
    },
    "prob_skin_abs_reason": {
        "ru": "Гной/флюктуация — осмотр хирурга",
        "en": "Pus/fluctuation — surgeon exam",
        "kz": "Ірің — хирург қарауы",
    },
    "prob_skin_atop_name": {
        "ru": "Атопический дерматит",
        "en": "Atopic dermatitis",
        "kz": "Атопиялық дерматит",
    },
    "prob_skin_atop_reason": {
        "ru": "Зуд/хроническое течение — дерматолог",
        "en": "Itch/chronic course — dermatologist",
        "kz": "Қышыну/созылмалы ағым — дерматолог",
    },
    # --- probable conditions: limb ---
    "prob_limb_dorso_name": {
        "ru": "Дорсопатия с корешковым синдромом",
        "en": "Dorsopathy with radicular syndrome",
        "kz": "Түбірлік синдромы бар дорсопатия",
    },
    "prob_limb_dorso_reason": {
        "ru": "Боль в спине/конечности ± онемение",
        "en": "Back/limb pain ± numbness",
        "kz": "Арқа/аяқ-қол ауырсынуы ± ұю",
    },
    "prob_limb_injury_name": {
        "ru": "Травма конечности (ушиб/растяжение)",
        "en": "Limb injury (bruise/strain)",
        "kz": "Аяқ-қол жарақаты (соғылу/созылу)",
    },
    "prob_limb_injury_reason": {
        "ru": "Связь с нагрузкой/травмой",
        "en": "Linked to load/trauma",
        "kz": "Жүктеме/жарақатпен байланыс",
    },
    "prob_limb_dvt_name": {
        "ru": "Тромбоз глубоких вен (исключить при одностороннем отёке)",
        "en": "Deep vein thrombosis (rule out if one-sided edema)",
        "kz": "Терең вена тромбозы (біржақты ісікте жоққа шығару)",
    },
    "prob_limb_dvt_reason": {
        "ru": "Односторонний отёк голени + боль в икре",
        "en": "One-sided calf edema + calf pain",
        "kz": "Балтырдың біржақты ісінуі + ауырсыну",
    },
    # --- probable conditions: general ---
    "prob_gen_r69_name": {
        "ru": "Состояние требует очной дифференциации",
        "en": "Requires in-person differentiation",
        "kz": "Күндізгі саралау қажет",
    },
    "prob_gen_r69_reason": {
        "ru": "Неспецифическая симптоматика — очный осмотр терапевта",
        "en": "Nonspecific symptoms — GP exam",
        "kz": "Бейспецификалық симптомдар — терапевт қарауы",
    },
    "prob_gen_ari_name": {
        "ru": "Острая респираторная инфекция",
        "en": "Acute respiratory infection",
        "kz": "Жедел респираторлық инфекция",
    },
    "prob_gen_ari_reason": {
        "ru": "Лихорадка + катаральные симптомы",
        "en": "Fever + catarrhal symptoms",
        "kz": "Қызба + катаралды симптомдар",
    },
    "prob_gen_obesity_name": {
        "ru": "Ожирение",
        "en": "Obesity",
        "kz": "Семіздік",
    },
    "prob_gen_obesity_reason": {
        "ru": "ИМТ {bmi}",
        "en": "BMI {bmi}",
        "kz": "ДСИ {bmi}",
    },
    # --- diet: surgery fasting ---
    "diet_surg_regime": {
        "ru": "СТРОГИЙ ГОЛОД: ничего не есть и не пить до осмотра хирурга",
        "en": "STRICT FASTING: eat and drink nothing until surgeon exam",
        "kz": "ҚАТАҢ АШТЫҚ: хирург қарауына дейін ештеңе жеуге және ішуге болмайды",
    },
    "diet_surg_reason": {
        "ru": "Подозрение на острую хирургическую патологию (аппендицит/непроходимость/кровотечение). Еда и вода повышают риск перитонита и аспирации при экстренной операции.",
        "en": "Suspected acute surgical pathology (appendicitis/obstruction/bleeding). Food and water raise peritonitis and aspiration risk.",
        "kz": "Жедел хирургиялық патология күдігі (аппендицит/өтімсіздік/қан кету). Тағам мен су перитонит және аспирация қаупін арттырады.",
    },
    "diet_surg_warning": {
        "ru": "НЕ ЕШЬТЕ и НЕ ПЕЙТЕ. Не принимайте анальгетики/спазмолитики — они стирают картину. Вызовите 103.",
        "en": "DO NOT EAT or DRINK. Do not take analgesics — they mask the picture. Call emergency.",
        "kz": "ЖЕМЕҢІЗ және ІШПЕҢІЗ. Ауырсынуды басатын дәрі ішпеңіз — көріністі бұзады. 103 шақырыңыз.",
    },
    # --- diet: diabetes (Table No.9) ---
    "diet_diab_regime": {
        "ru": "Стол №9 (щадящий, контроль гликемии): 3 основных приёма + 1–2 перекуса, без сахара",
        "en": "Table No.9 (glycemic control): 3 main meals + 1–2 snacks, no sugar",
        "kz": "№9 үстел (гликемияны бақылау): 3 негізгі ас + 1–2 тіскебасар, қантсыз",
    },
    "diet_diab_reason": {
        "ru": "Подозрение на нарушение гликемии / диабет либо прямой запрос. Требуется подтверждение глюкозой крови.",
        "en": "Suspected glycemia/diabetes or direct request. Confirm with blood glucose.",
        "kz": "Гликемия/диабет күдігі немесе тікелей сұраныс. Қан глюкозасымен растау қажет.",
    },
    # --- diet: gentle ---
    "diet_gentle_regime": {
        "ru": "Щадящая диета (по типу столов №1/2/4 по переносимости): дробно 4–5 раз, тёплая мягкая пища",
        "en": "Gentle diet (tables No.1/2/4 as tolerated): 4–5 small warm meals",
        "kz": "Жұмсақ диета (№1/2/4 үстелдер типі): күніне 4–5 рет жылы жұмсақ тағам",
    },
    "diet_gentle_reason": {
        "ru": "Гастроэнтерологическая симптоматика или ИМТ вне нормы / прямой запрос пользователя.",
        "en": "GI symptoms or abnormal BMI / direct user request.",
        "kz": "Гастроэнтерологиялық симптомдар немесе ДСИ нормадан тыс / тікелей сұраныс.",
    },
    # --- diet: none indicated ---
    "diet_none_regime": {
        "ru": "Специальная лечебная диета не показана",
        "en": "No special therapeutic diet indicated",
        "kz": "Арнайы емдік диета көрсетілмеген",
    },
    "diet_none_reason": {
        "ru": "Гастроэнтерологических/метаболических показаний нет и прямого запроса на диету не было. Достаточно обычного сбалансированного питания.",
        "en": "No GI/metabolic indications and no direct diet request. Regular balanced nutrition is enough.",
        "kz": "Гастроэнтерологиялық/метаболикалық көрсеткіштер жоқ және диетаға тікелей сұраныс болмады. Кәдімгі теңгерімді тамақтану жеткілікті.",
    },
    # --- actions: doctor map ---
    "doctor_chest": {
        "ru": "кардиолог (а при острой боли — скорая, затем кардиолог)",
        "en": "cardiologist (or emergency for acute pain, then cardiologist)",
        "kz": "кардиолог (жедел ауырсынуда — жедел жәрдем, содан кейін кардиолог)",
    },
    "doctor_abdomen": {
        "ru": "хирург очно при острой боли / гастроэнтеролог при хронической",
        "en": "surgeon in person for acute pain / gastroenterologist for chronic",
        "kz": "жедел ауырсынуда хирург / созылмалыда гастроэнтеролог",
    },
    "doctor_head": {
        "ru": "невролог (а при FAST-признаках — скорая)",
        "en": "neurologist (or emergency for FAST signs)",
        "kz": "невролог (FAST белгілерінде — жедел жәрдем)",
    },
    "doctor_skin": {
        "ru": "дерматолог (а при быстром распространении/гное — хирург)",
        "en": "dermatologist (or surgeon if spreading/pus)",
        "kz": "дерматолог (жайылса/іріңде — хирург)",
    },
    "doctor_limb": {
        "ru": "травматолог/невролог",
        "en": "traumatologist/neurologist",
        "kz": "травматолог/невролог",
    },
    "doctor_general": {
        "ru": "терапевт",
        "en": "GP / therapist",
        "kz": "терапевт",
    },
    # --- actions: RED ---
    "act_red_1": {
        "ru": "1. НЕМЕДЛЕННО вызовите скорую — 103 (или 112). Не садитесь за руль сами.",
        "en": "1. Call emergency NOW — 103 (or 112). Do not drive yourself.",
        "kz": "1. ШҰҒЫЛ жедел жәрдем шақырыңыз — 103 (немесе 112). Өзіңіз көлік жүргізбеңіз.",
    },
    "act_red_2": {
        "ru": "2. Обеспечьте покой, доступ воздуха; сядьте/лягте, ослабьте одежду.",
        "en": "2. Rest, fresh air; sit/lie down, loosen clothing.",
        "kz": "2. Тыныштық, таза ауа; отырыңыз/жатыңыз, киімді босатыңыз.",
    },
    "act_red_3": {
        "ru": "3. При боли в груди: разжевать аспирин 150–300 мг ТОЛЬКО если нет аллергии/кровотечения и скорая одобрила по телефону.",
        "en": "3. For chest pain: chew aspirin 150–300 mg ONLY if no allergy/bleeding and dispatcher approves.",
        "kz": "3. Кеуде ауырсынуында: аспирин 150–300 мг тек аллергия/қан кету жоқ болса және диспетчер рұқсат етсе.",
    },
    "act_red_4": {
        "ru": "4. Запишите время начала симптомов и все принятые препараты — передайте бригаде.",
        "en": "4. Note onset time and all drugs taken — hand to the crew.",
        "kz": "4. Басталу уақытын және ішкен дәрілерді жазыңыз — бригадаға беріңіз.",
    },
    "act_red_5": {
        "ru": "5. После стабилизации — срочно к врачу: {see_doctor}.",
        "en": "5. After stabilization — urgently to: {see_doctor}.",
        "kz": "5. Тұрақтанған соң — шұғыл: {see_doctor}.",
    },
    # --- actions: ORANGE ---
    "act_orange_1": {
        "ru": "1. В ближайшие часы — очный осмотр врача; при ухудшении — 103.",
        "en": "1. In-person exam within hours; if worse — emergency.",
        "kz": "1. Алдағы сағаттарда дәрігерге көрініңіз; нашарласа — 103.",
    },
    "act_orange_2": {
        "ru": "2. Измерьте температуру, АД, пульс; зафиксируйте динамику симптомов.",
        "en": "2. Measure temperature, BP, pulse; track dynamics.",
        "kz": "2. Температура, АҚ, пульс өлшеңіз; динамиканы бақылаңыз.",
    },
    "act_orange_3": {
        "ru": "3. Возьмите документы, список лекарств и аллергий.",
        "en": "3. Take documents, drug and allergy list.",
        "kz": "3. Құжаттар, дәрі мен аллергия тізімін алыңыз.",
    },
    "act_orange_4": {
        "ru": "4. Профильный врач: {see_doctor}.",
        "en": "4. Specialist: {see_doctor}.",
        "kz": "4. Бейінді дәрігер: {see_doctor}.",
    },
    # --- actions: YELLOW ---
    "act_yellow_1": {
        "ru": "1. В ближайшие 1–3 дня — плановый визит к врачу.",
        "en": "1. Routine visit within 1–3 days.",
        "kz": "1. 1–3 күнде жоспарлы дәрігерге барыңыз.",
    },
    "act_yellow_2": {
        "ru": "2. Ведите дневник симптомов 48–72 часа (что/когда/провоцирует).",
        "en": "2. Keep a symptom diary 48–72 h (what/when/triggers).",
        "kz": "2. 48–72 сағ симптом күнделігін жүргізіңіз.",
    },
    "act_yellow_3": {
        "ru": "3. Профильный врач: {see_doctor}.",
        "en": "3. Specialist: {see_doctor}.",
        "kz": "3. Бейінді дәрігер: {see_doctor}.",
    },
    # --- actions: GREEN ---
    "act_green_1": {
        "ru": "1. Острых показаний к экстренной помощи нет — наблюдайте 24–48 часов.",
        "en": "1. No acute emergency indications — observe 24–48 h.",
        "kz": "1. Жедел шұғыл көрсеткіш жоқ — 24–48 сағ бақылаңыз.",
    },
    "act_green_2": {
        "ru": "2. При усилении/новых симптомах — повторный скрининг или визит к врачу.",
        "en": "2. If worse/new symptoms — repeat screening or see a doctor.",
        "kz": "2. Күшейсе/жаңа симптом шықса — қайта скрининг немесе дәрігер.",
    },
    "act_green_3": {
        "ru": "3. Для профилактики — {see_doctor} планово.",
        "en": "3. For prevention — {see_doctor}, routine.",
        "kz": "3. Алдын алу үшін — {see_doctor}, жоспарлы.",
    },
    # --- actions: top-condition honesty line ---
    "act_top_line": {
        "ru": "Возможные причины для обсуждения с врачом (не диагноз, требуется очно): {name} ({icd}), вероятность: {band}.",
        "en": "Possible cause to discuss with a doctor (not a diagnosis), likelihood: {band} — {name} ({icd}).",
        "kz": "Дәрігермен талқыланатын мүмкін себеп (диагноз емес, бетпе-бет қаралу қажет), ықтималдығы: {band} — {name} ({icd}).",
    },
    # --- actions: surgery fasting prefix ---
    "forbid_surgery": {
        "ru": "Категорически НЕ есть и НЕ пить до осмотра хирурга; не принимать обезболивающие.",
        "en": "Strictly DO NOT eat or drink before surgeon exam; no painkillers.",
        "kz": "Хирург қарауына дейін ішіп-жеуге ҚАТАҢ тыйым; ауырсынуды басатын дәрі ішпеңіз.",
    },
    # --- evidence titles ---
    "ev_who": {
        "ru": "ВОЗ — рекомендации по первичной помощи",
        "en": "WHO — primary care recommendations",
        "kz": "ДДҰ — алғашқы көмек ұсынымдары",
    },
    "ev_heart": {
        "ru": "PubMed — HEART score для боли в груди (ID: 32979527)",
        "en": "PubMed — HEART score for chest pain (ID: 32979527)",
        "kz": "PubMed — кеуде ауырсынуына HEART шкаласы (ID: 32979527)",
    },
}

# ---------------------------------------------------------------------------
# Builder copy: list-valued entries (recommended/forbidden/menu/forbidden-actions).
# ---------------------------------------------------------------------------

LIST_MESSAGES: dict[str, dict[str, list[str]]] = {
    "diet_surg_forbidden": {
        "ru": ["Любая еда", "Вода и напитки", "Слабительные и обезболивающие без назначения", "Грелка на живот"],
        "en": ["Any food", "Water and drinks", "Laxatives and painkillers without prescription", "Heating pad on abdomen"],
        "kz": ["Кез келген тағам", "Су және сусындар", "Тағайындаусыз іш жүргізетін және ауырсынуды басатын дәрілер", "Ішке жылытқыш"],
    },
    "diet_diab_recommended": {
        "ru": ["Овощи 400–500 г/сут", "Цельнозерновые вместо белого хлеба", "Нежирный белок: курица, рыба, бобовые",
               "Кисломолочные без сахара", "Вода вместо соков/газировки"],
        "en": ["Vegetables 400–500 g/day", "Whole grains instead of white bread",
               "Lean protein: chicken, fish, legumes", "Sugar-free dairy", "Water instead of juices/soda"],
        "kz": ["Көкөніс 400–500 г/тәул", "Ақ нан орнына дәнді дақылдар",
               "Майсыз ақуыз: тауық, балық, бұршақ", "Қантсыз сүт өнімдері", "Шырын/газды су орнына су"],
    },
    "diet_diab_forbidden": {
        "ru": ["Сахар, мёд, сладости", "Белый хлеб и выпечка", "Сладкие напитки и соки", "Алкоголь", "Фастфуд и трансжиры"],
        "en": ["Sugar, honey, sweets", "White bread and pastries", "Sweet drinks and juices", "Alcohol", "Fast food and trans fats"],
        "kz": ["Қант, бал, тәттілер", "Ақ нан және бәліш", "Тәтті сусындар мен шырындар", "Алкоголь", "Фастфуд және трансмайлар"],
    },
    "diet_diab_menu": {
        "ru": ["Завтрак: овсянка на воде + яйцо + овощи",
               "Обед: суп овощной + курица/рыба + гречка",
               "Перекус: йогурт без сахара + орехи 20–30 г",
               "Ужин: рыба + овощи на пару"],
        "en": ["Breakfast: oatmeal + egg + vegetables",
               "Lunch: vegetable soup + chicken/fish + buckwheat",
               "Snack: sugar-free yogurt + nuts 20–30 g",
               "Dinner: fish + steamed vegetables"],
        "kz": ["Таңғы ас: сұлы ботқасы + жұмыртқа + көкөніс",
               "Түскі ас: көкөніс сорпасы + тауық/балық + қарақұмық",
               "Тіскебасар: қантсыз йогурт + жаңғақ 20–30 г",
               "Кешкі ас: балық + буға піскен көкөніс"],
    },
    "diet_gentle_recommended": {
        "ru": ["Каши на воде (рис, овсянка)", "Супы-пюре", "Отварное/паровое нежирное мясо и рыба",
               "Печёные овощи", "Вода 1.5–2 л/сут (если нет ограничений кардиолога/нефролога)"],
        "en": ["Porridge with water (rice, oatmeal)", "Pureed soups", "Boiled/steamed lean meat and fish",
               "Baked vegetables", "Water 1.5–2 L/day (unless restricted)"],
        "kz": ["Судағы ботқалар (күріш, сұлы)", "Езбе сорпалар", "Қайнатылған/буға піскен майсыз ет пен балық",
               "Пештегі көкөністер", "Су 1.5–2 л/тәул (шектеу болмаса)"],
    },
    "diet_gentle_forbidden": {
        "ru": ["Жирное, жареное, копчёное", "Острое и маринады", "Алкоголь", "Кофе натощак", "Свежая выпечка, бобовые при вздутии"],
        "en": ["Fatty, fried, smoked", "Spicy and marinades", "Alcohol", "Coffee on empty stomach", "Fresh pastries, legumes if bloated"],
        "kz": ["Майlı, қуырылған, ысталған", "Ащы және маринадтар", "Алкоголь", "Ашқарынға кофе", "Жаңа бәліш, кепкенде бұршақ"],
    },
    "diet_gentle_menu": {
        "ru": ["Завтрак: рисовая каша + банан",
               "Обед: суп-пюре из кабачка + индейка + картофель",
               "Полдник: печёное яблоко",
               "Ужин: рыба на пару + морковь/кабачок"],
        "en": ["Breakfast: rice porridge + banana",
               "Lunch: zucchini puree soup + turkey + potato",
               "Snack: baked apple",
               "Dinner: steamed fish + carrot/zucchini"],
        "kz": ["Таңғы ас: күріш ботқасы + банан",
               "Түскі ас: кәді езбе сорпасы + күркетауық + картоп",
               "Тіскебасар: пештегі алма",
               "Кешкі ас: буға піскен балық + сәбіз/кәді"],
    },
    "diet_none_recommended": {
        "ru": ["Овощи и фрукты ежедневно", "Достаточный белок", "Вода по жажде"],
        "en": ["Vegetables and fruits daily", "Enough protein", "Water as desired"],
        "kz": ["Күнде көкөніс пен жеміс", "Жеткілікті ақуыз", "Шөлге қарай су"],
    },
    "forbid_list": {
        "ru": [
            "Не занимайтесь самолечением антибиотиками и гормонами без назначения.",
            "Не прикладывайте грелку к животу при острой боли.",
            "Не вскрывайте гнойники дома.",
            "Не откладывайте вызов 103 при жизнеугрожающих признаках (боль в груди >15 мин, FAST, кровотечение, анафилаксия).",
        ],
        "en": [
            "Do not self-medicate with antibiotics or hormones.",
            "Do not apply a heating pad to acute abdominal pain.",
            "Do not open abscesses at home.",
            "Do not delay emergency for life-threats (chest pain >15 min, FAST, bleeding, anaphylaxis).",
        ],
        "kz": [
            "Антибиотик пен гормонмен өздігінен емделмеңіз.",
            "Жедел іш ауырсынуында жылытқыш баспаңыз.",
            "Іріңдікті үйде ашпаңыз.",
            "Өмірге қауіпті белгілерде 103 шақыруды кешіктірмеңіз.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Per-lang keyword hint sets (moved verbatim from the tripled builder branches).
# ---------------------------------------------------------------------------

_SURG_HINT_BASE = ["справа внизу", "миграция", "подвздош", "подвздошная", "аппендицит", "твёрдый", "твердый"]

KW_SURG_HINT: dict[str, list[str]] = {
    "ru": list(_SURG_HINT_BASE),
    "en": [*_SURG_HINT_BASE, "right lower", "migrat", "migrating", "migration", "rigid"],
    "kz": [*_SURG_HINT_BASE, "оң жақ"],
}

_FAST_HINT_BASE = ["перекос", "онемела", "онемение", "речь", "речи", "инсульт"]

KW_FAST_HINT: dict[str, list[str]] = {
    "ru": [*_FAST_HINT_BASE, "слабость руки"],
    "en": [*_FAST_HINT_BASE, "face droop", "stroke"],
    "kz": [*_FAST_HINT_BASE, "бет қисаюы"],
}

KW_ABD_DIAB: dict[str, list[str]] = {
    "ru": ["диабет", "жажда"],
    "en": ["диабет", "diabetes", "жажда"],
    "kz": ["диабет", "қант", "шөлдеу"],
}

KW_GEN_FEVER: dict[str, list[str]] = {
    "ru": ["температура", "лихорадка"],
    "en": ["температура", "fever", "қызба"],
    "kz": ["температура", "қызба"],
}
