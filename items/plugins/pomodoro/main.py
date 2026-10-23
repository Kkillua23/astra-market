"""Помодоро — пример плагина Astra: узлы команд, виджет, события и фразы.

Таймер живёт в процессе плагина (поток раз в секунду) и сохраняется в хранилище, поэтому
переживает перезапуск Astra. Конец фазы — уведомление и (по настройке) голос.
"""

import threading
import time
from dataclasses import asdict, dataclass

import astra_sdk as astra


@dataclass
class Timer:
    phase: str = "idle"  # idle | work | break
    ends_at: float = 0.0  # time.time(), когда фаза закончится
    paused_left: float | None = None  # секунд осталось, если на паузе
    round: int = 0
    total: float = 0.0  # длина фазы, секунд (для полоски прогресса)
    work_min: int = 25
    break_min: int = 5

    def left(self) -> float:
        if self.paused_left is not None:
            return self.paused_left
        return max(0.0, self.ends_at - time.time())


LOCK = threading.Lock()
STATE = Timer()


def _save() -> None:
    astra.storage.set("timer", asdict(STATE))


def _setting(key: str, fallback: int) -> int:
    value = astra.settings.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return fallback
    return int(value)


def start(work: int | None = None, rest: int | None = None) -> str:
    with LOCK:
        STATE.work_min = work or _setting("work", 25)
        STATE.break_min = rest or _setting("break", 5)
        STATE.round = 1
        _begin("work")
    return astra.t("started", minutes=STATE.work_min)


def _begin(phase: str) -> None:
    minutes = STATE.work_min if phase == "work" else STATE.break_min
    STATE.phase = phase
    STATE.total = minutes * 60
    STATE.ends_at = time.time() + STATE.total
    STATE.paused_left = None
    _save()


def stop() -> str:
    with LOCK:
        STATE.phase = "idle"
        STATE.paused_left = None
        _save()
    return astra.t("stopped")


def pause() -> str:
    with LOCK:
        if STATE.phase == "idle" or STATE.paused_left is not None:
            return astra.t("nothing")
        STATE.paused_left = STATE.left()
        _save()
    return astra.t("paused")


def resume() -> str:
    with LOCK:
        if STATE.paused_left is None:
            return astra.t("nothing")
        STATE.ends_at = time.time() + STATE.paused_left
        STATE.paused_left = None
        _save()
    return astra.t("resumed")


def _announce(text: str) -> None:
    astra.notify(text)
    if astra.settings.get("speak", True):
        astra.speak(text)


def _tick() -> None:
    """Раз в секунду: фаза закончилась — следующая (или конец всех кругов)."""
    while True:
        time.sleep(1)
        message = None
        with LOCK:
            if STATE.phase == "idle" or STATE.paused_left is not None or STATE.left() > 0:
                continue
            if STATE.phase == "work":
                _begin("break")
                message = astra.t("breakTime", minutes=STATE.break_min)
            elif STATE.round >= _setting("rounds", 4):
                STATE.phase = "idle"
                _save()
                message = astra.t("allDone")
            else:
                STATE.round += 1
                _begin("work")
                message = astra.t("workTime", round=STATE.round)
        if message:
            try:
                _announce(message)
            except astra.AstraError as err:
                astra.log.warning("Не удалось сообщить о смене фазы: %s", err)


# --- события --------------------------------------------------------------------------------


@astra.on_event("startup")
def on_startup(_data: object) -> None:
    """Восстановить таймер после перезапуска и запустить «часы»."""
    saved = astra.storage.get("timer")
    if isinstance(saved, dict):
        with LOCK:
            for key, value in saved.items():
                if hasattr(STATE, key):
                    setattr(STATE, key, value)
    threading.Thread(target=_tick, name="pomodoro-tick", daemon=True).start()
    astra.log.info("Помодоро готов: %s", STATE.phase)


@astra.on_event("game_mode")
def on_game_mode(data: dict) -> None:
    if data.get("state") == "enter" and astra.settings.get("pause_in_games", True):
        if STATE.phase != "idle" and STATE.paused_left is None:
            pause()
            astra.notify(astra.t("pausedForGame"))


@astra.on_event("phrase", phrases=["начни помодоро", "запусти помодоро", "start pomodoro"])
def phrase_start(text: str, slots: dict, ctx: astra.Context) -> str:
    return start()


@astra.on_event("phrase", phrases=["останови помодоро", "стоп помодоро", "stop pomodoro"])
def phrase_stop(text: str, slots: dict, ctx: astra.Context) -> str:
    return stop()


# --- узлы команд ----------------------------------------------------------------------------


@astra.register_node(
    "start",
    title={"ru": "Помодоро: начать", "en": "Pomodoro: start"},
    description={
        "ru": "Запускает таймер «работа — перерыв». Пустое значение — из настроек плагина.",
        "en": "Starts the work–break timer. Empty values come from the plugin settings.",
    },
    icon="timer",
    params={
        "work": {
            "type": "integer",
            "label": {"ru": "Работа, минут", "en": "Work, minutes"},
            "default": 25,
            "min": 1,
            "max": 180,
        },
        "break": {
            "type": "integer",
            "label": {"ru": "Перерыв, минут", "en": "Break, minutes"},
            "default": 5,
            "min": 1,
            "max": 60,
        },
    },
    subtitle={"ru": "{work} / {break} мин", "en": "{work} / {break} min"},
)
def node_start(params: dict, ctx: astra.Context) -> astra.NodeResult:
    message = start(int(params["work"]), int(params["break"]))
    return astra.NodeResult(message=message, vars={"pomodoro_phase": "work"})


@astra.register_node(
    "control",
    title={"ru": "Помодоро: пауза / стоп", "en": "Pomodoro: pause / stop"},
    description={
        "ru": "Пауза, продолжение или остановка таймера.",
        "en": "Pause, resume or stop the timer.",
    },
    icon="timer",
    params={
        "action": {
            "type": "select",
            "label": {"ru": "Действие", "en": "Action"},
            "options": {
                "pause": {"ru": "Пауза", "en": "Pause"},
                "resume": {"ru": "Продолжить", "en": "Resume"},
                "stop": {"ru": "Остановить", "en": "Stop"},
            },
            "default": "pause",
        }
    },
    subtitle={"ru": "{action}", "en": "{action}"},
)
def node_control(params: dict, ctx: astra.Context) -> astra.NodeResult:
    action = {"pause": pause, "resume": resume, "stop": stop}[params["action"]]
    return astra.NodeResult(message=action(), vars={"pomodoro_phase": STATE.phase})


# --- виджет ---------------------------------------------------------------------------------


def _clock(seconds: float) -> str:
    total = round(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


@astra.register_widget(
    "timer",
    title={"ru": "Помодоро", "en": "Pomodoro"},
    description={"ru": "Таймер «работа — перерыв»", "en": "Work–break timer"},
    icon="timer",
    sizes=["S", "M"],
    default_size="M",
    interval=1,
)
def timer_widget(ctx: astra.Context) -> list[dict]:
    with LOCK:
        phase, paused = STATE.phase, STATE.paused_left is not None
        left, total, rnd = STATE.left(), STATE.total, STATE.round
    if phase == "idle":
        minutes = _setting("work", 25)
        return [
            {"type": "stat", "label": astra.t("ready"), "value": _clock(minutes * 60)},
            {"type": "button", "label": astra.t("start"), "action": "start", "style": "primary"},
        ]
    label = astra.t("work" if phase == "work" else "break")
    blocks: list[dict] = [
        {
            "type": "stat",
            "label": f"{label} · {astra.t('round', round=rnd)}",
            "value": _clock(left),
            "hint": astra.t("onPause") if paused else None,
        },
        {"type": "progress", "value": 1 - left / total if total else 0},
    ]
    if paused:
        blocks.append({"type": "button", "label": astra.t("resume"), "action": "resume"})
    else:
        blocks.append({"type": "button", "label": astra.t("pause"), "action": "pause"})
    blocks.append({"type": "button", "label": astra.t("stop"), "action": "stop"})
    return blocks


@astra.widget_action("timer", "start")
def widget_start(ctx: astra.Context) -> None:
    start()


@astra.widget_action("timer", "pause")
def widget_pause(ctx: astra.Context) -> None:
    pause()


@astra.widget_action("timer", "resume")
def widget_resume(ctx: astra.Context) -> None:
    resume()


@astra.widget_action("timer", "stop")
def widget_stop(ctx: astra.Context) -> None:
    stop()
