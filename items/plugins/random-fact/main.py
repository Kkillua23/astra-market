"""Случайный факт — пример плагина Astra: инструмент для ИИ, виджет с кнопкой и фраза.

Факты лежат в facts/ru.txt и facts/en.txt (по одному в строке). В настройках можно
попросить, чтобы факты придумывал ИИ — для этого плагин просит разрешение «ai».
"""

import random
from pathlib import Path

import astra_sdk as astra

HERE = Path(__file__).resolve().parent


def _load(lang: str) -> list[str]:
    path = HERE / "facts" / f"{lang}.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


FACTS = {"ru": _load("ru"), "en": _load("en")}


def pick(lang: str, exclude: str | None = None) -> str:
    """Новый факт: от ИИ (если так выбрано в настройках) или из встроенного списка."""
    if astra.settings.get("source") == "ai":
        topic = astra.settings.get("topic") or astra.t("anyTopic")
        try:
            return astra.ask_ai(astra.t("prompt", topic=topic), model="fast")
        except astra.AstraError as err:
            astra.log.warning("ИИ недоступен (%s) — беру встроенный факт", err)
    facts = FACTS.get(lang) or FACTS["en"]
    return random.choice([f for f in facts if f != exclude] or facts)  # noqa: S311


@astra.register_tool(
    "get",
    title={"ru": "Вспоминаю факт", "en": "Recalling a fact"},
    description={
        "ru": "Случайный интересный факт. Вызывай, когда человек просит рассказать факт.",
        "en": "A random fun fact. Call it when the user asks for a fact.",
    },
    icon="lightbulb",
)
def get_fact(args: dict, ctx: astra.Context) -> str:
    return pick(ctx.language)


def _current(lang: str) -> str:
    saved = astra.storage.get("current")
    if isinstance(saved, dict) and saved.get("lang") == lang and saved.get("text"):
        return str(saved["text"])
    fact = pick(lang)
    astra.storage.set("current", {"lang": lang, "text": fact})
    return fact


@astra.register_widget(
    "fact",
    title={"ru": "Случайный факт", "en": "Random fact"},
    description={"ru": "Новый факт по кнопке", "en": "A new fact at a click"},
    icon="lightbulb",
    sizes=["M", "L"],
    default_size="M",
    interval=3600,
)
def fact_widget(ctx: astra.Context) -> list[dict]:
    blocks: list[dict] = [{"type": "text", "text": _current(ctx.language)}]
    if ctx.size == "L":
        source = astra.t("fromAi") if astra.settings.get("source") == "ai" else astra.t("fromList")
        blocks.append({"type": "text", "text": source, "style": "caption"})
    blocks.append({"type": "button", "label": astra.t("next"), "action": "next"})
    return blocks


@astra.widget_action("fact", "next")
def next_fact(ctx: astra.Context) -> None:
    saved = astra.storage.get("current") or {}
    fact = pick(ctx.language, exclude=saved.get("text"))
    astra.storage.set("current", {"lang": ctx.language, "text": fact})


@astra.on_event("phrase", phrases=["расскажи факт", "случайный факт", "tell me a fact"])
def fact_phrase(text: str, slots: dict, ctx: astra.Context) -> str:
    """Фраза срабатывает сразу, без ИИ: ответ звучит голосом или приходит в чат."""
    return pick(ctx.language)
