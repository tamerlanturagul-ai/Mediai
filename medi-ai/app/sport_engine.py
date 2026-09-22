"""Алгоритм реалистичного расчёта спорта MediAI: темп, сроки, противопоказания."""
from __future__ import annotations

from .schemas import SportPlanRequest
from .triage_engine import bmi_category, calc_bmi


_ACTIVITY_FACTOR = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "athlete": 1.9,
}


def _bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    s = 5 if sex == "male" else (-161 if sex == "female" else -78)
    return round(10 * weight_kg + 6.25 * height_cm - 5 * age + s, 1)


def build_sport_plan(req: SportPlanRequest) -> dict:
    bmi = calc_bmi(req.weight_kg, req.height_cm)
    cat = bmi_category(bmi)
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

    # --- Запрет ударного бега при ИМТ > 30 ---
    if bmi > 30:
        contraindications.append(
            "Ударный бег и прыжки ЗАПРЕЩЕНЫ при ИМТ > 30 (высокая нагрузка на колени, позвоночник, сердце)."
        )
        warnings.append("Замените бег ходьбой, велотренажёром, плаванием, эллипсом до снижения ИМТ < 30.")

    if req.age >= 50:
        warnings.append("Возраст 50+: перед интенсивными нагрузками — ЭКГ, АД-контроль, консультация терапевта/кардиолога.")
    if bmi >= 35:
        warnings.append("ИМТ ≥ 35: только низкоударные нагрузки + медицинское сопровождение (эндокринолог).")

    if req.goal == "lose":
        # Безопасный дефицит 15–20%, темп 0.5–1% массы тела в неделю, не более ~0.5–1 кг/нед
        target_kcal = round(tdee * 0.82, 1)
        weekly_loss = round(min(max(req.weight_kg * 0.0075, 0.4), 1.0), 2)
        tempo_text = f"{weekly_loss} кг/нед (0.5–1% массы тела — безопасный физиологический темп)"
        # Условная цель: −5–10% массы как первый этап
        target_loss = round(req.weight_kg * 0.07, 1)
        timeline_weeks = round(target_loss / weekly_loss, 1) if weekly_loss else 0
        timeline_text = (
            f"Первый реалистичный этап −{target_loss} кг (~7% массы) займёт ≈{timeline_weeks} нед. "
            "Быстрее — только за счёт воды/мышц, с откатом. Устойчивый результат — 12–24 недели."
        )
        training = [
            "3–5×/нед ходьба быстрым шагом 40–60 мин (пульс 60–70% от max ≈ 220 − возраст).",
            "2×/нед силовая на все группы мышц (резинки/гантели, 8–12 повт., 2–3 подхода).",
            "Ежедневно 8–10 тыс. шагов; сон 7–8 ч.",
        ]
        if bmi <= 30:
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
        tempo_text = f"~{monthly_gain} кг/мес (мышцы растут медленно: 0.25–0.5 кг/мес у новичков — норма)"
        timeline_weeks = 16.0
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
        tempo_text = "+2–5% к рабочим весам в месяц (у любителей) — реалистичный темп"
        timeline_weeks = 12.0
        timeline_text = "Плато — норма каждые 6–10 недель; прогрессия через периодизацию и технику, а не ежедневный максимум."
        training = [
            "3–4×/нед: база 3–6 повт., 3–5 подходов, отдых 2–3 мин.",
            "Техника > вес; разминка 10 мин + мобильность.",
            "Делoad-неделя каждый 5–6-й недельный цикл.",
        ]
        nutrition = [f"Поддержание/лёгкий профицит: ~{target_kcal} ккал.", "Белок 1.8–2.2 г/кг."]
    elif req.goal == "endurance":
        target_kcal = round(tdee, 1)
        tempo_text = "+10% к объёму в неделю (правило 10%) — безопасный прирост выносливости"
        timeline_weeks = 12.0
        timeline_text = "База выносливости строится 3–6 месяцев; первые сдвиги МПК — через 6–8 недель зоны 2."
        training = [
            "80% объёма — зона 2 (можно говорить фразами), 20% — интервалы.",
            "3–4×/нед бег/вело/плавание + 1× силовая.",
            "Сон и восстановление — часть плана.",
        ]
        nutrition = [f"Поддержание: ~{target_kcal} ккал.", "Углеводы 5–7 г/кг в дни объёма, электролиты на >90 мин."]
    else:  # maintain
        tempo_text = "0 кг/нед — поддержание формы"
        timeline_weeks = 4.0
        timeline_text = "Форма поддерживается 3–4 тренировками в неделю; пропуски >2 недель откатывают выносливость."
        training = [
            "3×/нед смешанные: 2 силовые + 1 кардио 30–40 мин.",
            "10 тыс. шагов, активность каждый день.",
        ]
        nutrition = [f"Поддержание: ~{target_kcal} ккал.", "Белок 1.4–1.8 г/кг."]

    # Пользовательские противопоказания — пробрасываем в предупреждения дословно
    for c in req.contraindications:
        if c and c not in warnings:
            warnings.append(f"Учтено противопоказание пользователя: {c}")

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
    }
