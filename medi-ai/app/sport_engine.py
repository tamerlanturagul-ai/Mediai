"""Алгоритм реалистичного расчёта спорта MediAI: темп, сроки, противопоказания."""
from __future__ import annotations

from .i18n import resolve_lang
from .schemas import SportPlanRequest
from .triage_engine import bmi_category, calc_bmi

_ACTIVITY_FACTOR = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "athlete": 1.9,
}


# Mifflin-St Jeor (1990): BMR = 10*W + 6.25*H − 5*A + s,
# где s = +5 (мужчины) / −161 (женщины).
# Для sex="other" берём среднее двух констант (5 + (−161)) / 2 = −78.
# Это задокументированное допущение, а не магическое число.
_MIFFLIN_S_MALE = 5
_MIFFLIN_S_FEMALE = -161
_MIFFLIN_S_OTHER = round((_MIFFLIN_S_MALE + _MIFFLIN_S_FEMALE) / 2)  # = −78


def _bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    if sex == "male":
        s = _MIFFLIN_S_MALE
    elif sex == "female":
        s = _MIFFLIN_S_FEMALE
    else:
        s = _MIFFLIN_S_OTHER
    return round(10 * weight_kg + 6.25 * height_cm - 5 * age + s, 1)


def _lang_of(req: SportPlanRequest) -> str:
    """Deprecated alias: extracts req.lang via app.i18n.resolve_lang (kept for backward compat)."""
    return resolve_lang(getattr(req, "lang", "ru"))


def parq_positive(req: SportPlanRequest) -> bool:
    """True, если есть хотя бы один положительный ответ PAR-Q."""
    flags = (
        req.parq_chest_pain,
        req.parq_dizziness,
        req.parq_joint_problem,
        req.parq_heart_condition,
        req.parq_diabetes,
        req.parq_age50_unsupervised,
    )
    return any(flags) or bool((req.parq_other or "").strip())


# --- Локализованные строки (RU/EN/KZ): запреты, предупреждения, честность ---

_BAN_CONTRA = {
    "ru": "Ударный бег и прыжки ЗАПРЕЩЕНЫ при ИМТ ≥ 30 (высокая нагрузка на колени, позвоночник, сердце).",
    "en": "High-impact running and jumping are PROHIBITED at BMI ≥ 30 (heavy load on knees, spine and heart).",
    "kz": "ДСИ ≥ 30 болғанда соққы жүгіру мен секіруге ТЫЙЫМ САЛЫНАДЫ (тізе, омыртқа және жүрекке жоғары жүктеме).",
}

_BAN_WARN = {
    "ru": "Замените бег ходьбой, велотренажёром, плаванием, эллипсом до снижения ИМТ ниже 30.",
    "en": "Replace running with walking, stationary bike, swimming or elliptical until BMI drops below 30.",
    "kz": "ДСИ 30-дан төмендегенше жүгіруді жаяу жүрумен, велотренажермен, жүзумен, эллипспен алмастырыңыз.",
}

_AGE_WARN = {
    "ru": "Возраст 50+: перед интенсивными нагрузками — ЭКГ, АД-контроль, консультация терапевта/кардиолога.",
    "en": "Age 50+: ECG, blood pressure monitoring and GP/cardiologist clearance before intense exercise.",
    "kz": "Жас 50+: қарқынды жүктемелер алдында ЭКГ, АҚ бақылауы, терапевт/кардиолог кеңесі.",
}

_BMI35_WARN = {
    "ru": "ИМТ ≥ 35: только низкоударные нагрузки + медицинское сопровождение (эндокринолог).",
    "en": "BMI ≥ 35: low-impact loads only + medical supervision (endocrinologist).",
    "kz": "ДСИ ≥ 35: тек төмен соққы жүктемелер + медициналық бақылау (эндокринолог).",
}

_USER_CONTRA_PREFIX = {
    "ru": "Учтено противопоказание пользователя: ",
    "en": "User contraindication noted: ",
    "kz": "Пайдаланушының қарсы көрсетілімі ескерілді: ",
}

# Честная оговорка: темп и сроки — ориентир, не гарантия (все цели, все языки).
_HONEST_SUFFIX = {
    "ru": " Это ориентир, не гарантия: фактический темп зависит от сна, стресса, точности подсчёта калорий и состояния здоровья.",
    "en": " This is an estimate, not a guarantee: actual pace depends on sleep, stress, calorie-tracking accuracy and health conditions.",
    "kz": " Бұл бағдар, кепілдік емес: нақты қарқын ұйқыға, күйзеліске, калория санау дәлдігіне және денсаулық жағдайына байланысты.",
}

_PARQ_WARN = {
    "ru": "PAR-Q: есть положительный ответ — сначала получите допуск врача к тренировкам; до этого только низкоударные нагрузки (ходьба, плавание, вело, эллипс).",
    "en": "PAR-Q: positive answer flagged — get doctor clearance before training; until then low-impact loads only (walk, swim, bike, elliptical).",
    "kz": "PAR-Q: оң жауап белгіленді — алдымен жаттығуға дәрігердің рұқсатын алыңыз; оған дейін тек төмен соққы жүктемелер (жаяу жүру, жүзу, вело, эллипс).",
}

# PAR-Q: принудительный низкоударный план (без бега/прыжков/интервалов), все языки.
_PARQ_PLAN = {
    "ru": [
        "Ходьба 3–5×/нед по 30–60 мин (пульс 60–70% от max ≈ 220 − возраст).",
        "Плавание или велотренажёр 2×/нед по 30–45 мин.",
        "Эллипс 1–2×/нед по 20–30 мин + лёгкая силовая с резинками 1–2×/нед.",
        "Ударные кардионагрузки исключены до допуска врача.",
    ],
    "en": [
        "Walking 3–5×/week, 30–60 min (heart rate 60–70% of max ≈ 220 − age).",
        "Swimming or stationary bike 2×/week, 30–45 min.",
        "Elliptical 1–2×/week, 20–30 min + light resistance-band strength 1–2×/week.",
        "High-impact cardio is excluded until doctor clearance.",
    ],
    "kz": [
        "Жаяу жүру 3–5×/апта, 30–60 мин (пульс max ≈ 220 − жас мөлшерінің 60–70%).",
        "Жүзу немесе велотренажер 2×/апта, 30–45 мин.",
        "Эллипс 1–2×/апта, 20–30 мин + резинкалармен жеңіл күш жаттығуы 1–2×/апта.",
        "Соққы кардиожүктемелер дәрігер рұқсатына дейін алынып тасталады.",
    ],
}


def build_sport_plan(req: SportPlanRequest) -> dict:
    lang = _lang_of(req)
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    cat = bmi_category(bmi, lang)
    bmr = _bmr_mifflin(req.sex, req.weight_kg, req.height_cm, req.age)
    factor = _ACTIVITY_FACTOR.get(req.activity_level, 1.375)
    tdee = round(bmr * factor, 1)

    contraindications: list[str] = list(req.contraindications or [])
    warnings: list[str] = []
    training: list[str] = []
    nutrition: list[str] = []
    target_kcal = tdee
    tempo_text = ""
    timeline_weeks = 0.0
    timeline_text = ""

    # --- Запрет ударного бега при ИМТ ≥ 30 (все три языка) ---
    if bmi >= 30:
        contraindications.append(_BAN_CONTRA[lang])
        warnings.append(_BAN_WARN[lang])

    if req.age >= 50:
        warnings.append(_AGE_WARN[lang])
    if bmi >= 35:
        warnings.append(_BMI35_WARN[lang])

    if parq_positive(req):
        warnings.append(_PARQ_WARN[lang])

    if req.goal == "lose":
        # Безопасный дефицит 15–20%, темп 0.5–1% массы тела в неделю, не более ~0.5–1 кг/нед
        target_kcal = round(tdee * 0.82, 1)
        weekly_loss = round(min(max(req.weight_kg * 0.0075, 0.4), 1.0), 2)
        # Условная цель: −5–10% массы как первый этап
        target_loss = round(req.weight_kg * 0.07, 1)
        timeline_weeks = round(target_loss / weekly_loss, 1) if weekly_loss else 0
        if lang == "en":
            tempo_text = f"{weekly_loss} kg/week (0.5–1% of body weight — safe physiological rate)"
            timeline_text = (
                f"First realistic stage −{target_loss} kg (~7% of weight) takes ≈{timeline_weeks} weeks. "
                "Faster loss is water/muscle with rebound. Lasting results take 12–24 weeks."
            )
            training = [
                "Brisk walking 3–5×/week, 40–60 min (heart rate 60–70% of max ≈ 220 − age).",
                "Full-body strength 2×/week (bands/dumbbells, 8–12 reps, 2–3 sets).",
                "8–10k steps daily; sleep 7–8 h.",
            ]
            if bmi < 30:
                training.append("1×/week easy interval run 20–30 min — only with no joint pain.")
            else:
                training.append("Swimming/cycling 2×/week, 30–45 min instead of running.")
            nutrition = [
                f"Deficit ≈15–20%: target {target_kcal} kcal/day vs maintenance {tdee} kcal.",
                "Protein 1.6–2.0 g/kg to preserve muscle.",
                "Fiber 25–30 g/day, water 30 ml/kg.",
            ]
        elif lang == "kz":
            tempo_text = f"{weekly_loss} кг/апта (дене салмағының 0,5–1% — қауіпсіз физиологиялық қарқын)"
            timeline_text = (
                f"Алғашқы шынайы кезең −{target_loss} кг (~7% салмақ) ≈{timeline_weeks} апта алады. "
                "Одан жылдам — тек су/бұлшықет есебінен, қайта оралумен. Тұрақты нәтиже — 12–24 апта."
            )
            training = [
                "Жаяу жылдам жүру 3–5×/апта, 40–60 мин (пульс max ≈ 220 − жас мөлшерінің 60–70%).",
                "Барлық бұлшықетке күш жаттығуы 2×/апта (резинка/гантель, 8–12 қайталау, 2–3 тәсіл).",
                "Күніне 8–10 мың қадам; ұйқы 7–8 сағ.",
            ]
            if bmi < 30:
                training.append("1×/апта жеңіл интервалды жүгіру 20–30 мин — буын ауырсынуы болмаса ғана.")
            else:
                training.append("Жүгірудің орнына жүзу/вело 2×/апта, 30–45 мин.")
            nutrition = [
                f"Тапшылық ≈15–20%: бағдар {target_kcal} ккал/тәул., қолдау {tdee} ккал.",
                "Бұлшықетті сақтау үшін ақуыз 1,6–2,0 г/кг.",
                "Жасұнық 25–30 г/тәул., су 30 мл/кг.",
            ]
        else:
            tempo_text = f"{weekly_loss} кг/нед (0.5–1% массы тела — безопасный физиологический темп)"
            timeline_text = (
                f"Первый реалистичный этап −{target_loss} кг (~7% массы) займёт ≈{timeline_weeks} нед. "
                "Быстрее — только за счёт воды/мышц, с откатом. Устойчивый результат — 12–24 недели."
            )
            training = [
                "3–5×/нед ходьба быстрым шагом 40–60 мин (пульс 60–70% от max ≈ 220 − возраст).",
                "2×/нед силовая на все группы мышц (резинки/гантели, 8–12 повт., 2–3 подхода).",
                "Ежедневно 8–10 тыс. шагов; сон 7–8 ч.",
            ]
            if bmi < 30:
                training.append("1×/нед интервальная лёгкая пробежка 20–30 мин — только при отсутствии боли в суставах.")
            else:
                training.append("Плавание/вело 2×/нед по 30–45 мин вместо бега.")
            nutrition = [
                f"Дефицит ≈15–20%: ориентир {target_kcal} ккал/сут при поддержании {tdee} ккал.",
                "Белок 1.6–2.0 г/кг массы тела для сохранения мышц.",
                "Клетчатка 25–30 г/сут, вода 30 мл/кг.",
            ]
    elif req.goal == "gain":
        target_kcal = round(tdee * 1.10, 1)
        monthly_gain = 1.0 if req.age < 40 else 0.7
        timeline_weeks = 16.0
        if lang == "en":
            tempo_text = f"~{monthly_gain} kg/month (muscles grow slowly: 0.25–0.5 kg/month in beginners is normal)"
            timeline_text = (
                "Visible strength gains — 6–8 weeks; visible hypertrophy — 4–6 months of regular training. "
                "Gaining faster than 1 kg/month is mostly fat."
            )
            training = [
                "Progressive strength 3×/week (squat, deadlift, press, pull-ups/rows), 4–8 reps for strength.",
                "Sleep 7–9 h; 7–8k steps.",
                "Cardio 1–2×/week, 20 min for the heart, no extremes.",
            ]
            nutrition = [
                f"Light surplus +10%: target {target_kcal} kcal/day.",
                "Protein 1.8–2.2 g/kg, creatine monohydrate 3–5 g/day (if no kidney contraindications).",
            ]
        elif lang == "kz":
            tempo_text = f"~{monthly_gain} кг/ай (бұлшықет баяу өседі: жаңадан бастағандарда 0,25–0,5 кг/ай — қалыпты)"
            timeline_text = (
                "Күштің елеулі өсуі — 6–8 апта; көрінерлік гипертрофия — 4–6 ай жүйелі жаттығу. "
                "1 кг/айдан жылдам жинау — негізінен май."
            )
            training = [
                "Үдемелі күш жаттығуы 3×/апта (отырып-тұру, тартылу, сығымдау, тарту), күшке 4–8 қайталау.",
                "Ұйқы 7–9 сағ; 7–8 мың қадам.",
                "Жүрекке кардио 1–2×/апта, 20 мин, шектен шықпай.",
            ]
            nutrition = [
                f"Жеңіл артықшылық +10%: бағдар {target_kcal} ккал/тәул.",
                "Ақуыз 1,8–2,2 г/кг, креатин моногидраты 3–5 г/тәул. (бүйрек қарсы көрсетілімдері болмаса).",
            ]
        else:
            tempo_text = f"~{monthly_gain} кг/мес (мышцы растут медленно: 0.25–0.5 кг/мес у новичков — норма)"
            timeline_text = (
                "Заметный прирост силы — 6–8 недель; визуальная гипертрофия — 4–6 месяцев регулярных тренировок. "
                "Набор быстрее 1 кг/мес — преимущественно жир."
            )
            training = [
                "3×/нед силовая прогрессия (присед, тяга, жим, подтягивания/тяги), 4–8 повт. на силу.",
                "Профицит сна 7–9 ч; шаги 7–8 тыс.",
                "Кардио 1–2×/нед по 20 мин для сердца, без фанатизма.",
            ]
            nutrition = [
                f"Лёгкий профицит +10%: ориентир {target_kcal} ккал/сут.",
                "Белок 1.8–2.2 г/кг, креатин моногидрат 3–5 г/сут (при отсутствии противопоказаний почек).",
            ]
    elif req.goal == "strength":
        target_kcal = round(tdee * 1.05, 1)
        timeline_weeks = 12.0
        if lang == "en":
            tempo_text = "+2–5% to working weights per month (amateurs) — realistic pace"
            timeline_text = "Plateaus every 6–10 weeks are normal; progress via periodization and technique, not daily maxes."
            training = [
                "3–4×/week: compound lifts 3–6 reps, 3–5 sets, rest 2–3 min.",
                "Technique over weight; 10-min warm-up + mobility.",
                "Deload week every 5th–6th week.",
            ]
            nutrition = [f"Maintenance/light surplus: ~{target_kcal} kcal.", "Protein 1.8–2.2 g/kg."]
        elif lang == "kz":
            tempo_text = "Жұмыс салмағына айына +2–5% (әуесқойларда) — шынайы қарқын"
            timeline_text = "Әр 6–10 аптада плато — қалыпты; прогресс кезеңдеу мен техника арқылы, күнделікті максимум емес."
            training = [
                "3–4×/апта: базалық 3–6 қайталау, 3–5 тәсіл, демалу 2–3 мин.",
                "Салмақтан гөрі техника; 10 мин қыздырыну + мобильділік.",
                "Әр 5–6-шы аптада deload-апта.",
            ]
            nutrition = [f"Қолдау/жеңіл артықшылық: ~{target_kcal} ккал.", "Ақуыз 1,8–2,2 г/кг."]
        else:
            tempo_text = "+2–5% к рабочим весам в месяц (у любителей) — реалистичный темп"
            timeline_text = "Плато — норма каждые 6–10 недель; прогрессия через периодизацию и технику, а не ежедневный максимум."
            training = [
                "3–4×/нед: база 3–6 повт., 3–5 подходов, отдых 2–3 мин.",
                "Техника > вес; разминка 10 мин + мобильность.",
                "Делoad-неделя каждый 5–6-й недельный цикл.",
            ]
            nutrition = [f"Поддержание/лёгкий профицит: ~{target_kcal} ккал.", "Белок 1.8–2.2 г/кг."]
    elif req.goal == "endurance":
        target_kcal = round(tdee, 1)
        timeline_weeks = 12.0
        if lang == "en":
            tempo_text = "+10% volume per week (10% rule) — safe endurance gain"
            timeline_text = "Endurance base takes 3–6 months; first VO2max shifts after 6–8 weeks of zone 2."
            training = [
                "80% of volume in zone 2 (can speak in phrases), 20% intervals.",
                "3–4×/week run/bike/swim + 1× strength.",
                "Sleep and recovery are part of the plan.",
            ]
            nutrition = [f"Maintenance: ~{target_kcal} kcal.", "Carbs 5–7 g/kg on volume days, electrolytes beyond 90 min."]
        elif lang == "kz":
            tempo_text = "Аптасына көлемге +10% (10% ережесі) — төзімділіктің қауіпсіз өсуі"
            timeline_text = "Төзімділік негізі 3–6 айда құрылады; АҚТ-тағы алғашқы өзгерістер 2-аймақтың 6–8 аптасынан кейін."
            training = [
                "Көлемнің 80% — 2-аймақ (сөйлеммен сөйлеуге болады), 20% — интервалдар.",
                "3–4×/апта жүгіру/вело/жүзу + 1× күш.",
                "Ұйқы мен қалпына келу — жоспардың бөлігі.",
            ]
            nutrition = [f"Қолдау: ~{target_kcal} ккал.", "Көлем күндері көмірсу 5–7 г/кг, 90 мин-тан ұзаққа электролиттер."]
        else:
            tempo_text = "+10% к объёму в неделю (правило 10%) — безопасный прирост выносливости"
            timeline_text = "База выносливости строится 3–6 месяцев; первые сдвиги МПК — через 6–8 недель зоны 2."
            training = [
                "80% объёма — зона 2 (можно говорить фразами), 20% — интервалы.",
                "3–4×/нед бег/вело/плавание + 1× силовая.",
                "Сон и восстановление — часть плана.",
            ]
            nutrition = [f"Поддержание: ~{target_kcal} ккал.", "Углеводы 5–7 г/кг в дни объёма, электролиты на >90 мин."]
    else:  # maintain
        timeline_weeks = 4.0
        if lang == "en":
            tempo_text = "0 kg/week — maintaining fitness"
            timeline_text = "Fitness is maintained with 3–4 sessions per week; gaps over 2 weeks roll back endurance."
            training = [
                "3×/week mixed: 2 strength + 1 cardio 30–40 min.",
                "10k steps, active every day.",
            ]
            nutrition = [f"Maintenance: ~{target_kcal} kcal.", "Protein 1.4–1.8 g/kg."]
        elif lang == "kz":
            tempo_text = "0 кг/апта — форманы ұстау"
            timeline_text = "Форма аптасына 3–4 жаттығумен сақталады; 2 аптадан астам үзіліс төзімділікті төмендетеді."
            training = [
                "3×/апта аралас: 2 күш + 1 кардио 30–40 мин.",
                "10 мың қадам, күнде белсенділік.",
            ]
            nutrition = [f"Қолдау: ~{target_kcal} ккал.", "Ақуыз 1,4–1,8 г/кг."]
        else:
            tempo_text = "0 кг/нед — поддержание формы"
            timeline_text = "Форма поддерживается 3–4 тренировками в неделю; пропуски >2 недель откатывают выносливость."
            training = [
                "3×/нед смешанные: 2 силовые + 1 кардио 30–40 мин.",
                "10 тыс. шагов, активность каждый день.",
            ]
            nutrition = [f"Поддержание: ~{target_kcal} ккал.", "Белок 1.4–1.8 г/кг."]

    # Честная оговорка ко всем срокам/темпам (все цели, все языки).
    timeline_text = timeline_text + _HONEST_SUFFIX[lang]

    # PAR-Q: положительный ответ — план принудительно низкоударный (все языки).
    if parq_positive(req):
        training = list(_PARQ_PLAN[lang])

    # Пользовательские противопоказания — пробрасываем в предупреждения дословно
    for c in req.contraindications:
        if c and c not in warnings:
            warnings.append(f"{_USER_CONTRA_PREFIX[lang]}{c}")

    return {
        "bmi": bmi,
        "bmi_category": cat,
        "bmr_kcal": bmr,
        "tdee_kcal": tdee,
        "target_kcal": target_kcal,
        "weekly_tempo_kg": tempo_text,
        "timeline_weeks": timeline_weeks,
        "timeline_text": timeline_text,
        "training_plan": training,
        "nutrition_hint": nutrition,
        "contraindications": contraindications,
        "warnings": warnings,
        "lang": lang,
    }
