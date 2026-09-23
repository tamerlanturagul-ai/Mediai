"""Question banks 6 zones x 3 langs (extracted from triage_engine, TASK-003)."""
from __future__ import annotations

from ..i18n import resolve_lang
from ..schemas import TriageInitialRequest, TriageQuestion
from ..services.triage_service import _text
from .rules import _kw_hit, _normalize_med_text, normalize_zone

_QUESTION_BANK_RU: dict[str, list[tuple[str, str, str]]] = {
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

_QUESTION_BANK_EN: dict[str, list[tuple[str, str, str]]] = {
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

_QUESTION_BANK_KZ: dict[str, list[tuple[str, str, str]]] = {
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


def generate_initial_questions(req: TriageInitialRequest) -> list[TriageQuestion]:
    """Вернуть ровно 3 клинических уточняющих вопроса на языке req.lang."""
    lang = resolve_lang(getattr(req, "lang", "ru"))
    zone = normalize_zone(req.body_zone)
    # Эвристика: если текст явно указывает на другую зону — корректируем.
    t = _text(req)
    tn = _normalize_med_text(t)
    if any(_kw_hit(k, tn) for k in ["аппендицит", "справа внизу живота", "подвздош", "подвздошная", "appendicitis", "right lower", "migrating", "migration"]) and zone != "abdomen":
        zone = "abdomen"
    if any(_kw_hit(k, tn) for k in ["грудин", "грудина", "грудиной", "за грудиной", "отдаёт в руку", "отдает в руку", "жмет в груди", "chest pain", "pressing"]) and zone != "chest":
        zone = "chest"
    if any(_kw_hit(k, tn) for k in ["перекос лица", "перекос", "онемела рука", "онемела", "нарушение речи", "речи", "инсульт", "face droop", "stroke", "бет қисаюы"]) and zone != "head":
        zone = "head"

    bank_map = {"ru": _QUESTION_BANK_RU, "en": _QUESTION_BANK_EN, "kz": _QUESTION_BANK_KZ}
    bank = bank_map[lang].get(zone, bank_map[lang]["general"])
    options = _OPTIONS_I18N[lang]
    return [
        TriageQuestion(id=qid, text=text, reason=reason, options=list(options))
        for (qid, text, reason) in bank[:3]
    ]

