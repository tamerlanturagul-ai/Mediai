"""Клиническая логика триажа MediAI: вопросы, BMI, риски, диета, действия."""
from __future__ import annotations

import re
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
# Каталог заболеваний для мега-меню (с кодами МКБ-10), 3 языка
# ---------------------------------------------------------------------------

CONDITIONS_CATALOG_RU: Dict[str, List[ConditionItem]] = {
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

CONDITIONS_CATALOG_EN: Dict[str, List[ConditionItem]] = {
    "cardiology": [
        ConditionItem(name="Angina pectoris", icd10="I20", category="cardiology",
                      urgency_hint="Pressing retrosternal pain — rule out ACS, call emergency"),
        ConditionItem(name="Acute myocardial infarction", icd10="I21", category="cardiology",
                      urgency_hint="RED: burning pain >15 min, dyspnea, cold sweat — emergency now"),
        ConditionItem(name="Essential hypertension", icd10="I10", category="cardiology",
                      urgency_hint="BP ≥140/90 repeatedly — GP/cardiologist, routine"),
        ConditionItem(name="Atrial fibrillation", icd10="I48", category="cardiology",
                      urgency_hint="Palpitations, dyspnea — cardiologist, ECG"),
    ],
    "gastroenterology": [
        ConditionItem(name="Gastroesophageal reflux disease", icd10="K21",
                      category="gastroenterology", urgency_hint="Heartburn — gastroenterologist"),
        ConditionItem(name="Gastric ulcer", icd10="K25", category="gastroenterology",
                      urgency_hint="Hunger/night pain, black stool — see doctor urgently"),
        ConditionItem(name="Gastritis", icd10="K29", category="gastroenterology",
                      urgency_hint="Diet No.1/2, gastroenterologist"),
        ConditionItem(name="Irritable bowel syndrome", icd10="K59",
                      category="gastroenterology", urgency_hint="Gastroenterologist, FODMAP protocol"),
        ConditionItem(name="Type 2 diabetes mellitus", icd10="E11",
                      category="gastroenterology", urgency_hint="Thirst, frequent urination — glucose, endocrinologist"),
        ConditionItem(name="Obesity", icd10="E66",
                      category="gastroenterology", urgency_hint="BMI ≥30 — endocrinologist, diet, activity"),
    ],
    "neurology": [
        ConditionItem(name="Migraine", icd10="G43", category="neurology",
                      urgency_hint="Pulsating unilateral pain with aura — neurologist"),
        ConditionItem(name="Tension-type headache", icd10="G44.2", category="neurology",
                      urgency_hint="Pressing bilateral — neurologist/GP"),
        ConditionItem(name="Stroke (suspected)", icd10="I63/I64", category="neurology",
                      urgency_hint="RED: FAST — face droop, arm weakness, speech — emergency now"),
        ConditionItem(name="Dorsopathy / back pain", icd10="M54", category="neurology",
                      urgency_hint="Neurologist; red flags: saddle numbness, urine retention — emergency"),
    ],
    "dermatology": [
        ConditionItem(name="Atopic dermatitis", icd10="L20", category="dermatology",
                      urgency_hint="Dermatologist, emollients"),
        ConditionItem(name="Psoriasis", icd10="L40", category="dermatology",
                      urgency_hint="Dermatologist, routine"),
        ConditionItem(name="Cellulitis / erysipelas", icd10="L03", category="dermatology",
                      urgency_hint="Rapid spread + fever — surgeon/infectious disease, urgent"),
        ConditionItem(name="Skin abscess", icd10="L02", category="dermatology",
                      urgency_hint="Abscess, fluctuation — surgeon, do not open at home"),
    ],
    "surgery": [
        ConditionItem(name="Acute appendicitis", icd10="K35", category="surgery",
                      urgency_hint="RED: pain migration to right iliac fossa + fever — emergency, fasting"),
        ConditionItem(name="Cholelithiasis / colic", icd10="K80", category="surgery",
                      urgency_hint="Right upper quadrant pain after fatty food — surgeon, ultrasound"),
        ConditionItem(name="Inguinal hernia", icd10="K40", category="surgery",
                      urgency_hint="Bulge, irreducible + pain — emergency (strangulation)"),
        ConditionItem(name="Intestinal obstruction (suspected)", icd10="K56",
                      category="surgery", urgency_hint="RED: distension, no stool/gas, vomiting — emergency, fasting"),
    ],
}

CONDITIONS_CATALOG_KZ: Dict[str, List[ConditionItem]] = {
    "кардиология": [
        ConditionItem(name="Стенокардия", icd10="I20", category="кардиология",
                      urgency_hint="Төс артындағы қысатын ауырсыну — ЖҚС жоққа шығару, 103 шақыру"),
        ConditionItem(name="Жедел миокард инфарктісі", icd10="I21", category="кардиология",
                      urgency_hint="RED: 15 мин-тан ұзақ күйдіретін ауырсыну, ентігу, суық тер — шұғыл 103"),
        ConditionItem(name="Эссенциалды гипертензия", icd10="I10", category="кардиология",
                      urgency_hint="АҚ ≥140/90 қайталанса — терапевт/кардиолог, жоспарлы"),
        ConditionItem(name="Жүрекше фибрилляциясы", icd10="I48", category="кардиология",
                      urgency_hint="Ырғақ бұзылысы, ентігу — кардиолог, ЭКГ"),
    ],
    "гастроэнтерология": [
        ConditionItem(name="Гастроэзофагеалды рефлюкс ауруы", icd10="K21",
                      category="гастроэнтерология", urgency_hint="Қыжыл — гастроэнтеролог"),
        ConditionItem(name="Асқазан жарасы", icd10="K25", category="гастроэнтерология",
                      urgency_hint="Аш/түнгі ауырсыну, қара нәжіс — шұғыл дәрігерге"),
        ConditionItem(name="Гастрит", icd10="K29", category="гастроэнтерология",
                      urgency_hint="№1/2 диета, гастроэнтеролог"),
        ConditionItem(name="Тітіркенген ішек синдромы", icd10="K59",
                      category="гастроэнтерология", urgency_hint="Гастроэнтеролог, FODMAP хаттамасы"),
        ConditionItem(name="2-типті қант диабеті", icd10="E11",
                      category="гастроэнтерология", urgency_hint="Шөлдеу, жиі зәр — глюкоза, эндокринолог"),
        ConditionItem(name="Семіздік", icd10="E66",
                      category="гастроэнтерология", urgency_hint="ДСИ ≥30 — эндокринолог, диета, белсенділік"),
    ],
    "неврология": [
        ConditionItem(name="Мигрень", icd10="G43", category="неврология",
                      urgency_hint="Аурасы бар біржақты солқылдаған ауырсыну — невролог"),
        ConditionItem(name="Кернеулі бас ауруы", icd10="G44.2", category="неврология",
                      urgency_hint="Қысатын екіжақты — невролог/терапевт"),
        ConditionItem(name="Инсульт (күдік)", icd10="I63/I64", category="неврология",
                      urgency_hint="RED: FAST — бет қисаюы, қол әлсіздігі, сөйлеу — шұғыл 103"),
        ConditionItem(name="Дорсопатия / арқа ауруы", icd10="M54", category="неврология",
                      urgency_hint="Невролог; қызыл жалаулар: ұйып қалу, зәр іркілісі — 103"),
    ],
    "дерматология": [
        ConditionItem(name="Атопиялық дерматит", icd10="L20", category="дерматология",
                      urgency_hint="Дерматолог, эмоленттер"),
        ConditionItem(name="Псориаз", icd10="L40", category="дерматология",
                      urgency_hint="Дерматолог, жоспарлы"),
        ConditionItem(name="Целлюлит / рожа", icd10="L03", category="дерматология",
                      urgency_hint="Жылдам жайылу + қызба — хирург/инфекционист, шұғыл"),
        ConditionItem(name="Тері абсцессі", icd10="L02", category="дерматология",
                      urgency_hint="Іріңдік — хирург, үйде ашпау"),
    ],
    "хирургия": [
        ConditionItem(name="Жедел аппендицит", icd10="K35", category="хирургия",
                      urgency_hint="RED: ауырсынудың оң жаққа ығысуы + қызба — 103, аштық"),
        ConditionItem(name="Өт тас ауруы / шаншу", icd10="K80", category="хирургия",
                      urgency_hint="Майдан кейін оң қабырға асты ауырсынуы — хирург, УДЗ"),
        ConditionItem(name="Шап жарығы", icd10="K40", category="хирургия",
                      urgency_hint="Томпаю, орнына келмеу + ауырсыну — 103 (қысылу)"),
        ConditionItem(name="Ішек өтімсіздігі (күдік)", icd10="K56",
                      category="хирургия", urgency_hint="RED: кебу, нәжіс/газ жоқ, құсу — 103, аштық"),
    ],
}

CONDITIONS_CATALOG = CONDITIONS_CATALOG_RU


def _norm_lang(lang: str | None) -> str:
    l = (lang or "ru").lower()
    return l if l in ("ru", "en", "kz") else "ru"


def get_conditions_catalog(lang: str = "ru") -> Dict[str, List[ConditionItem]]:
    l = _norm_lang(lang)
    if l == "en":
        return CONDITIONS_CATALOG_EN
    if l == "kz":
        return CONDITIONS_CATALOG_KZ
    return CONDITIONS_CATALOG_RU


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def calc_bmi(weight_kg: float, height_cm: float) -> float:
    h_m = max(height_cm / 100.0, 0.5)
    return round(weight_kg / (h_m ** 2), 1)


_BMI_I18N = {
    "ru": ["Дефицит массы тела", "Норма", "Избыточная масса тела",
           "Ожирение I степени", "Ожирение II степени", "Ожирение III степени"],
    "en": ["Underweight", "Normal", "Overweight",
           "Obesity class I", "Obesity class II", "Obesity class III"],
    "kz": ["Салмақ тапшылығы", "Қалыпты", "Артық салмақ",
           "I дәрежелі семіздік", "II дәрежелі семіздік", "III дәрежелі семіздік"],
}

_BMI_SHORT_I18N = {
    "ru": ["Дефицит", "Норма", "Избыток", "Ожирение"],
    "en": ["Low", "Normal", "High", "Obese"],
    "kz": ["Тапшылық", "Қалыпты", "Артық", "Семіздік"],
}


def bmi_category(bmi: float, lang: str = "ru") -> str:
    l = _norm_lang(lang)
    full = _BMI_I18N[l]
    if bmi < 18.5:
        return full[0]
    if bmi < 25:
        return full[1]
    if bmi < 30:
        return full[2]
    if bmi < 35:
        return full[3]
    if bmi < 40:
        return full[4]
    return full[5]


def bmi_category_short(bmi: float, lang: str = "ru") -> str:
    l = _norm_lang(lang)
    s = _BMI_SHORT_I18N[l]
    if bmi < 18.5:
        return s[0]
    if bmi < 25:
        return s[1]
    if bmi < 30:
        return s[2]
    return s[3]


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
# Первичный скрининг: ровно 3 уточняющих вопроса (RU/EN/KZ)
# ---------------------------------------------------------------------------

_QUESTION_BANK_RU: Dict[str, List[Tuple[str, str, str]]] = {
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

_QUESTION_BANK_EN: Dict[str, List[Tuple[str, str, str]]] = {
    "chest": [
        ("chest_pressing", "Is the chest pain pressing, squeezing or burning and lasting more than 5–15 minutes?",
         "Rule out acute coronary syndrome (I20–I21)"),
        ("chest_breath", "Is there shortness of breath, cold sweat, nausea or fear of death with the pain?",
         "Screening for infarction / PE / pneumothorax"),
        ("chest_radiation", "Does the pain radiate to the left arm, shoulder, neck, jaw or back?",
         "Radiation is a typical sign of cardiac pain"),
    ],
    "abdomen": [
        ("abd_migration", "Has the pain moved to the lower right abdomen and worsens when walking/coughing?",
         "Rule out acute appendicitis (K35)"),
        ("abd_fever_vomit", "Is there fever ≥37.5°C, nausea or vomiting?",
         "Systemic signs of acute surgical pathology"),
        ("abd_tension", "Has the abdomen become hard, sharply painful, with bloating or no stool/gas?",
         "Rule out peritonitis / obstruction (K56)"),
    ],
    "head": [
        ("neuro_fast", "SUDDENLY: face droop, one-sided arm/leg weakness or numbness, speech problems?",
         "FAST stroke screening (I63/I64)"),
        ("neuro_thunder", "Did the pain start suddenly like a “thunderclap” — worst in life, with vomiting or fainting?",
         "Rule out subarachnoid hemorrhage / hypertensive crisis"),
        ("neuro_fever_neck", "Is there high fever, neck stiffness, rash?",
         "Rule out meningitis/encephalitis"),
    ],
    "skin": [
        ("skin_spread", "Is redness/swelling spreading fast (within hours), with increasing pain?",
         "Rule out cellulitis/erysipelas (L03) — sepsis risk"),
        ("skin_fever_pus", "Is there fever ≥38°C, pus, blisters, black crust or severe tenderness?",
         "Signs of bacterial infection / abscess (L02)"),
        ("skin_breath_allergy", "Is there lip/tongue swelling, breathing difficulty, whole-body rash after drug/food/bite?",
         "Rule out anaphylaxis — RED state"),
    ],
    "limb": [
        ("limb_trauma", "Was there trauma/fall, cracking sound, can you bear weight on the limb?",
         "Rule out fracture/dislocation"),
        ("limb_neuro", "Is there numbness, tingling, foot/hand weakness, urination problems or saddle numbness?",
         "Red flags of nerve root compression"),
        ("limb_swelling", "Is there sudden one-sided calf swelling, redness and calf pain, dyspnea or chest pain?",
         "Rule out deep vein thrombosis / PE"),
    ],
    "general": [
        ("gen_red_acute", "RIGHT NOW: severe chest pain, choking, fainting, seizures, coffee-ground vomit or black stool?",
         "Universal life-threat screening"),
        ("gen_fever", "Is there fever ≥38.5°C, chills, confusion or severe weakness?",
         "Sepsis/severe infection screening"),
        ("gen_dynamic", "Have symptoms sharply worsened in recent hours, with new severe pain or numbness?",
         "Dynamics assessment — ORANGE/RED marker"),
    ],
}

_QUESTION_BANK_KZ: Dict[str, List[Tuple[str, str, str]]] = {
    "chest": [
        ("chest_pressing", "Төс артындағы ауырсыну қысатын, жаншитын немесе күйдіретін, 5–15 минуттан ұзақ па?",
         "Жедел коронарлық синдромды жоққа шығару (I20–I21)"),
        ("chest_breath", "Ентігу, ауа жетіспеуі, суық тер, жүрек айну немесе өлім үрейі бар ма?",
         "Инфаркт / ТЭЛА / пневмоторакс скринингі"),
        ("chest_radiation", "Ауырсыну сол қолға, иыққа, мойынға, жаққа немесе арқаға беріле ме?",
         "Иррадиация — жүрек ауырсынуының типтік белгісі"),
    ],
    "abdomen": [
        ("abd_migration", "Ауырсыну оң жақ төменгі ішке ығысып, жүргенде/жөтелгенде күшейе ме?",
         "Жедел аппендицитті жоққа шығару (K35)"),
        ("abd_fever_vomit", "Температура ≥37.5°C, жүрек айну немесе құсу бар ма?",
         "Жедел хирургиялық патологияның жүйелі белгілері"),
        ("abd_tension", "Іш қатайып, басқанда қатты ауырып, кебу және нәжіс/газ іркілісі бар ма?",
         "Перитонит / өтімсіздікті жоққа шығару (K56)"),
    ],
    "head": [
        ("neuro_fast", "КЕНЕТТЕН: бет қисаюы, біржақты қол/аяқ әлсіздігі немесе ұюы, сөйлеу бұзылысы бар ма?",
         "FAST инсульт скринингі (I63/I64)"),
        ("neuro_thunder", "Ауырсыну кенеттен «найзағай соққысындай» — өмірдегі ең қатты, құсу немесе естен танумен басталды ма?",
         "Субарахноидалды қан кету / гипертон кризін жоққа шығару"),
        ("neuro_fever_neck", "Жоғары температура, шүйде сіресуі, бөртпе бар ма?",
         "Менингит/энцефалитті жоққа шығару"),
    ],
    "skin": [
        ("skin_spread", "Қызару/ісіну жылдам жайылып жатыр ма (сағаттар ішінде), ауырсыну күшейе ме?",
         "Целлюлит/рожаны жоққа шығару (L03) — сепсис қаупі"),
        ("skin_fever_pus", "Қызба ≥38°C, ірің, көпіршік, қара қабыршақ немесе қатты ауырсыну бар ма?",
         "Бактериялық инфекция / абсцесс белгілері (L02)"),
        ("skin_breath_allergy", "Ерін/тіл ісінуі, тыныс тарылуы, дәрі/тағам/шағудан кейін бүкіл денеде бөртпе бар ма?",
         "Анафилаксияны жоққа шығару — RED жағдай"),
    ],
    "limb": [
        ("limb_trauma", "Жарақат/құлау болды ма, сытыр естілді ме, аяқ-қолға сүйене аласыз ба?",
         "Сынық/шығуды жоққа шығару"),
        ("limb_neuro", "Ұю, шаншу, табан/білек әлсіздігі, зәр шығару мәселесі бар ма?",
         "Жүйке түбірі қысылуының қызыл жалаулары"),
        ("limb_swelling", "Балтырдың кенеттен біржақты ісінуі, қызаруы және ауырсынуы, ентігу бар ма?",
         "Терең вена тромбозын / ТЭЛА жоққа шығару"),
    ],
    "general": [
        ("gen_red_acute", "ҚАЗІР: кеудеде қатты ауырсыну, тұншығу, естен тану, құрысу, «кофе тұнбасы» құсу немесе қара нәжіс бар ма?",
         "Өмірге қауіпті жағдайлардың әмбебап скринингі"),
        ("gen_fever", "Температура ≥38.5°C, қалтырау, сана бұзылысы немесе қатты әлсіздік бар ма?",
         "Сепсис/ауыр инфекция скринингі"),
        ("gen_dynamic", "Соңғы сағаттарда симптомдар күрт күшейіп, жаңа қатты ауырсыну немесе ұю пайда болды ма?",
         "Динамиканы бағалау — ORANGE/RED маркері"),
    ],
}

_QUESTION_BANK = _QUESTION_BANK_RU

_OPTIONS_I18N = {
    "ru": ["Да", "Нет", "Не уверен(а)"],
    "en": ["Yes", "No", "Not sure"],
    "kz": ["Иә", "Жоқ", "Сенімді емеспін"],
}


def generate_initial_questions(req: TriageInitialRequest) -> List[TriageQuestion]:
    """Вернуть ровно 3 клинических уточняющих вопроса на языке req.lang."""
    lang = _norm_lang(getattr(req, "lang", "ru"))
    zone = normalize_zone(req.body_zone)
    # Эвристика: если текст явно указывает на другую зону — корректируем.
    t = _text(req)
    if any(k in t for k in ["аппендицит", "справа внизу живота", "подвздош", "appendicitis", "right lower", "аппендицит"]) and zone != "abdomen":
        zone = "abdomen"
    if any(k in t for k in ["грудин", "за грудиной", "отдаёт в руку", "жмет в груди", "chest pain", "pressing"]) and zone != "chest":
        zone = "chest"
    if any(k in t for k in ["перекос лица", "онемела рука", "нарушение речи", "инсульт", "face droop", "stroke", "бет қисаюы"]) and zone != "head":
        zone = "head"

    bank_map = {"ru": _QUESTION_BANK_RU, "en": _QUESTION_BANK_EN, "kz": _QUESTION_BANK_KZ}
    bank = bank_map[lang].get(zone, bank_map[lang]["general"])
    options = _OPTIONS_I18N[lang]
    return [
        TriageQuestion(id=qid, text=text, reason=reason, options=list(options))
        for (qid, text, reason) in bank[:3]
    ]


# ---------------------------------------------------------------------------
# Финальная оценка
# ---------------------------------------------------------------------------

_RED_PHRASES = ["да", "yes", "есть", "сильная", "резко", "внезапно", "не могу", "невозможно"]


def _answer_is_positive(answer: str) -> bool:
    a = (answer or "").strip().lower()
    if a in ("да", "yes", "есть", "имеется", "наблюдается", "иә", "бар", "болады"):
        return True
    # «да, ...» тоже считаем положительным
    if a.startswith("да") or a.startswith("yes") or a.startswith("иә"):
        return True
    return False


def _normalize_med_text(s: str) -> str:
    """Normalized lowercase text for word-boundary matching (Unicode-aware)."""
    return (s or "").lower().replace("ё", "е")


def _kw_pattern(kw: str) -> str:
    k = _normalize_med_text(kw)
    if k == "39":
        return r"\b39\b"
    if k == "38.5":
        return r"\b38[.,]5\b"
    if k == "температура 39":
        return r"\bтемпература\s*:?\s*39\b"
    if k == "температура 40":
        return r"\bтемпература\s*:?\s*40\b"
    if k == "fast":
        return r"\bfast\b"
    if k == "faint":
        # keep sensitivity to faint/fainting/faainted with word-start boundary
        return r"\bfaint\w*\b"
    if k == "fever":
        return r"\bfever\w*\b"
    if k == "анафилакси":
        # stem of анафилаксия/анафилактический — allow suffix, require word start
        return r"\bанафилакси\w*\b"
    return r"\b" + re.escape(k) + r"\b"


def _kw_hit(kw: str, text_norm: str) -> bool:
    try:
        return re.search(_kw_pattern(kw), text_norm, flags=re.UNICODE) is not None
    except re.error:
        return _normalize_med_text(kw) in text_norm


def _keyword_score(t: str) -> Tuple[float, List[str]]:
    """Эвристический скоринг по свободному тексту. Возвращает (баллы, флаги)."""
    score = 0.0
    flags: List[str] = []
    tn = _normalize_med_text(t)
    red_groups = [
        (["боль за грудиной", "давит в груди", "жжет в груди", "отдаёт в руку", "холодный пот", "удушье", "нехватка воздуха",
          "chest pain", "pressing chest", "cold sweat", "shortness of breath", "төс артындағы ауырсыну", "суық тер", "ентігу"], 38, "кардиальный красный флаг"),
        (["перекос лица", "онемела рука", "нарушение речи", "инсульт", "fast", "face droop", "arm weakness", "stroke", "бет қисаюы"], 42, "неврологический красный флаг (FAST)"),
        (["рвота кофейной", "черный стул", "мелена", "кровь в стуле", "кровотечение", "coffee-ground", "black stool", "bleeding", "қара нәжіс"], 40, "кровотечение ЖКТ"),
        (["острая боль справа внизу", "миграция боли", "твёрдый живот", "твердый живот", "доскообразный", "нет стула и газов", "задержка стула",
          "right lower", "migrating pain", "rigid abdomen", "оң жақ", "қатайған іш"], 36, "острая хирургическая патология"),
        (["анафилакси", "отёк губ", "отек губ", "отёк языка", "задыхаюсь", "anaphylaxis", "lip swelling", "анафилаксия"], 45, "анафилаксия"),
        (["температура 39", "температура 40", "38.5", "39", "озноб", "спутанность", "потеря сознания", "обморок", "судороги",
          "fever", "chills", "confusion", "faint", "қызба", "қалтырау"], 25, "системная тяжесть"),
        (["тошнота", "рвота", "лихорадка", "температура", "nausea", "vomiting", "жүрек айну", "құсу"], 10, "системные симптомы"),
    ]
    for keywords, pts, flag in red_groups:
        if any(_kw_hit(k, tn) for k in keywords):
            score += pts
            flags.append(flag)
    # Возраст и хронические маркеры
    if any(_kw_hit(k, tn) for k in ["диабет", "давление", "гипертония", "астма", "ибс", "инфаркт в прошлом", "diabetes", "hypertension", "asthma", "қант диабеті"]):
        score += 6
        flags.append("отягощённый анамнез")
    return score, flags


def evaluate_final(req: TriageFinalRequest) -> dict:
    t = _text(req)
    lang = _norm_lang(getattr(req, "lang", "ru"))
    zone = normalize_zone(req.body_zone)
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    bmi_cat = bmi_category(bmi, lang)

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
    unsure = sum(1 for a in req.answers if any(k in (a.answer or "").lower() for k in ["не уверен", "не знаю", "not sure", "сенімді емес"]))
    score += unsure * 4

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
    }


def _build_probable_conditions(
    zone: str, t: str, req: TriageFinalRequest, positives: int, bmi: float, lang: str = "ru"
) -> List[ProbableCondition]:
    l = _norm_lang(lang)
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
            surg_hint = any(k in t for k in ["справа внизу", "миграция", "подвздош", "аппендицит", "твёрдый", "твердый", "right lower", "migrat", "rigid"])
            base = 20 + positives * 14
            if surg_hint or positives >= 2:
                add("Acute appendicitis (suspected)", "K35", base + 15, "Right-sided migration + fever/nausea")
                add("Cholelithiasis / colic", "K80", base, "Abdominal pain linked to fatty food")
            else:
                add("Acute gastritis", "K29", base + 10, "Epigastric pain/discomfort")
                add("Gastric ulcer", "K25", base, "Hunger/night pain — rule out complication")
            add("Irritable bowel syndrome", "K59", 25, "Functional differential diagnosis")
            if bmi >= 30 or "диабет" in t or "diabetes" in t or "жажда" in t:
                add("Type 2 diabetes (screening)", "E11", 30, "Obesity/thirst — check glucose")
        elif zone == "head":
            fast_hint = any(k in t for k in ["перекос", "онемела", "речь", "инсульт", "face droop", "stroke"])
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
            if "температура" in t or "fever" in t or "қызба" in t:
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
            surg_hint = any(k in t for k in ["справа внизу", "миграция", "подвздош", "аппендицит", "твёрдый", "твердый", "оң жақ"])
            base = 20 + positives * 14
            if surg_hint or positives >= 2:
                add("Жедел аппендицит (күдік)", "K35", base + 15, "Ауырсынудың оңға ығысуы + қызба/жүрек айну")
                add("Өт тас ауруы / шаншу", "K80", base, "Іш ауырсынуы, майлы тағаммен байланыс")
            else:
                add("Жедел гастрит", "K29", base + 10, "Эпигастрийде ауырсыну/жайсыздық")
                add("Асқазан жарасы", "K25", base, "Аш/түнгі ауырсыну — асқынуды жоққа шығару")
            add("Тітіркенген ішек синдромы", "K59", 25, "Функционалды ажыратпа диагноз")
            if bmi >= 30 or "диабет" in t or "қант" in t or "шөлдеу" in t:
                add("2-типті қант диабеті (скрининг)", "E11", 30, "Семіздік/шөлдеу — глюкозаны тексеру")
        elif zone == "head":
            fast_hint = any(k in t for k in ["перекос", "онемела", "речь", "инсульт", "бет қисаюы"])
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
            if "температура" in t or "қызба" in t:
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


_GI_BLEED_SIGNALS = [
    "мелена", "черный стул", "рвота кофейной", "кровотечение",
    "bleeding", "black stool", "coffee-ground", "қара нәжіс",
    "кровь в стуле",
]

_ABDOMEN_SURGICAL_SIGNALS = [
    "аппендицит", "справа внизу", "подвздош", "твёрдый живот",
    "твердый живот", "нет стула", "непроходимость", "доскообразный",
]


def _surgery_suspected(zone: str, t: str, probable: List[ProbableCondition]) -> bool:
    tn = _normalize_med_text(t)
    if zone == "abdomen" and any(_kw_hit(k, tn) for k in _ABDOMEN_SURGICAL_SIGNALS):
        return True
    icds = " ".join(p.icd10 for p in probable)
    if "K35" in icds or "K56" in icds:
        return True
    # GI-bleed in ANY zone → strict fasting (zone-independent).
    if any(_kw_hit(k, tn) for k in _GI_BLEED_SIGNALS):
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
    zone: str, t: str, probable: List[ProbableCondition], requested: bool, bmi: float, lang: str = "ru"
) -> DietInfo:
    l = _norm_lang(lang)
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
        diabetes = any("E11" in p.icd10 for p in probable) or "диабет" in t or "diabetes" in t or "қант" in t
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
            actions.append(f"Differential to discuss: {top.name} ({top.icd10}), ~{top.probability}%.")
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
            actions.append(f"Дәрігермен талқылауға: {top.name} ({top.icd10}), ~{top.probability}%.")
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
