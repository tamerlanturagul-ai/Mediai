"""Disease catalogs RU/EN/KZ (extracted from triage_engine, TASK-003)."""
from __future__ import annotations

from typing import Dict, List

from ..schemas import ConditionItem
from .rules import _norm_lang


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

def get_conditions_catalog(lang: str = "ru") -> Dict[str, List[ConditionItem]]:
    l = _norm_lang(lang)
    if l == "en":
        return CONDITIONS_CATALOG_EN
    if l == "kz":
        return CONDITIONS_CATALOG_KZ
    return CONDITIONS_CATALOG_RU
