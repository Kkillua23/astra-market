"""Правила каталога Astra Market: что можно публиковать и как это проверяется.

Только стандартная библиотека. Приложение проверяет пакеты ещё раз при установке
(backend/market/package.py) — каталогу оно не доверяет.
"""

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TYPES = {"themes": "theme", "commands": "command", "plugins": "plugin"}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,6}(-[0-9A-Za-z.-]{1,20})?$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,19}$")
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
HTTPS_RE = re.compile(r"^https://\S{1,290}$")

MB = 1024 * 1024
SIZE_LIMITS = {"theme": 2 * MB, "command": 2 * MB, "plugin": 5 * MB}
MAX_FILES = 200
MANIFEST_MAX = 64 * 1024
PREVIEW_MAX = 512 * 1024
SCREENSHOT_MAX = MB
MAX_SCREENSHOTS = 6
CHANGELOG_MAX = 64 * 1024
ICON_MAX = 128 * 1024
MAX_TAGS = 5

PAYLOAD = {"theme": "theme.json", "command": "command.json"}
COMMON_FILES = {"manifest.json", "CHANGELOG.md", "preview.png", "README.md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
# Плагин — это код на Python и данные к нему. Исполняемых файлов и архивов в нём быть не может.
PLUGIN_EXT = {
    ".py", ".json", ".md", ".txt", ".csv", ".toml", ".yaml", ".yml", ".ini",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".wav", ".mp3", ".ogg",
}  # fmt: skip
BINARY_MAGIC = (b"MZ", b"\x7fELF", b"PK\x03\x04", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")
IMAGE_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}
PERMISSIONS = ("network", "files", "system", "shell", "ai")
# Обход разрешений Astra: такой код смотрит человек перед слиянием.
RISKY_MODULES = {
    "subprocess", "ctypes", "socket", "winreg", "_winapi", "multiprocessing", "pickle",
    "marshal", "importlib", "urllib", "http", "requests", "httpx", "aiohttp",
}  # fmt: skip
RISKY_CALLS = {
    "eval", "exec", "compile", "__import__", "os.system", "os.popen", "os.startfile",
    "os.remove", "os.unlink", "os.rmdir", "shutil.rmtree", "os.execv", "os.spawnv",
}  # fmt: skip

THEME_MODES = ("blobs", "nebula", "smoke")
THEME_RADII = ("compact", "default", "round")


@dataclass
class Report:
    """Ошибки не пускают элемент в каталог; предупреждения — повод посмотреть глазами."""

    errors: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def error(self, where: str, text: str) -> None:
        self.errors.append((where, text))

    def warn(self, where: str, text: str) -> None:
        self.warnings.append((where, text))


@dataclass
class Item:
    type: str
    id: str
    folder: Path
    manifest: dict[str, Any]
    payload: dict[str, Any] | None
    files: list[Path]


def parse_version(text: str) -> tuple[int, int, int]:
    major, minor, patch = (int(x) for x in text.split("-", 1)[0].split("."))
    return major, minor, patch


def read_json(path: Path, limit: int, report: Report, where: str) -> dict[str, Any] | None:
    if not path.is_file():
        report.error(where, f"нет файла {path.name}")
        return None
    if path.stat().st_size > limit:
        report.error(where, f"{path.name} больше {limit // 1024} КБ")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        report.error(where, f"{path.name}: не JSON ({err})")
        return None
    if not isinstance(data, dict):
        report.error(where, f"{path.name}: нужен объект {{…}}")
        return None
    return data


def _text(value: Any, max_len: int) -> bool:  # noqa: ANN401 — значение из JSON
    return (
        isinstance(value, dict)
        and set(value) == {"ru", "en"}
        and all(isinstance(v, str) and 0 < len(v.strip()) <= max_len for v in value.values())
    )


def _number(value: Any, low: float, high: float) -> bool:  # noqa: ANN401
    return isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high


def check_manifest(item_type: str, manifest: dict[str, Any], report: Report, where: str) -> None:
    if manifest.get("type", item_type) != item_type:
        report.error(where, f"type в manifest.json — не «{item_type}»")
    if "featured" in manifest:
        report.error(where, "featured задаёт владелец каталога в featured.json, не автор")
    if not _text(manifest.get("name"), 48):
        report.error(where, "name: нужен {'ru': …, 'en': …}, до 48 символов")
    if not _text(manifest.get("description"), 400):
        report.error(where, "description: нужен {'ru': …, 'en': …}, до 400 символов")
    author = manifest.get("author")
    if not isinstance(author, str) or not 0 < len(author.strip()) <= 80:
        report.error(where, "author: от 1 до 80 символов")
    if not VERSION_RE.match(str(manifest.get("version", ""))):
        report.error(where, "version: формат 1.2.3")
    tags = manifest.get("tags", [])
    if not isinstance(tags, list) or len(tags) > MAX_TAGS:
        report.error(where, f"tags: список до {MAX_TAGS} меток")
    elif not all(isinstance(t, str) and TAG_RE.match(t) for t in tags):
        report.error(where, "tags: латиница, цифры и «-», до 20 символов")
    if "min_app_version" in manifest and not VERSION_RE.match(str(manifest["min_app_version"])):
        report.error(where, "min_app_version: формат 1.2.3")
    homepage = manifest.get("homepage")
    if homepage is not None and not (isinstance(homepage, str) and HTTPS_RE.match(homepage)):
        report.error(where, "homepage: только https-ссылка")


def check_theme(theme: dict[str, Any], report: Report, where: str) -> None:
    """Зеркало схемы темы приложения (src/theme/schema.ts) — главное, без мелочей."""

    def color(value: Any) -> bool:  # noqa: ANN401
        return isinstance(value, str) and HEX_RE.match(value.strip()) is not None

    bg, glass = theme.get("background"), theme.get("glass")
    problems = []
    if theme.get("appearance") not in ("dark", "light"):
        problems.append("appearance")
    if not isinstance(bg, dict):
        problems.append("background")
    else:
        colors = bg.get("colors")
        checks = {
            "mode": bg.get("mode") in THEME_MODES,
            "colors": isinstance(colors, list)
            and 3 <= len(colors) <= 4
            and all(map(color, colors)),
            "base": color(bg.get("base")),
            "speed": _number(bg.get("speed"), 0.1, 3),
            "count": isinstance(bg.get("count"), int) and 3 <= bg["count"] <= 6,
            "glow": _number(bg.get("glow"), 0, 2),
            "grain": _number(bg.get("grain"), 0, 1),
            "contrast": _number(bg.get("contrast"), 0.5, 2),
        }
        problems += [f"background.{k}" for k, ok in checks.items() if not ok]
    if not isinstance(glass, dict):
        problems.append("glass")
    else:
        checks = {
            "tint": color(glass.get("tint")),
            "opacity": _number(glass.get("opacity"), 0, 0.9),
            "blur": _number(glass.get("blur"), 0, 80),
            "saturation": _number(glass.get("saturation"), 100, 220),
            "border": _number(glass.get("border"), 0, 0.4),
        }
        problems += [f"glass.{k}" for k, ok in checks.items() if not ok]
    if not color(theme.get("accent")):
        problems.append("accent")
    if theme.get("radius") not in THEME_RADII:
        problems.append("radius")
    if problems:
        report.error(where, f"theme.json: неверные поля — {', '.join(problems)}")


def check_command(doc: dict[str, Any], report: Report, where: str) -> None:
    command = doc.get("command")
    if doc.get("format") != "astra-command" or not isinstance(command, dict):
        report.error(where, "command.json: нужен экспорт команды из Astra (format astra-command)")
        return
    graph = command.get("graph")
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if not isinstance(nodes, list) or not nodes or len(nodes) > 300:
        report.error(where, "command.json: в графе от 1 до 300 узлов")
    elif not any(
        isinstance(n, dict) and str(n.get("type", "")).startswith("trigger.") for n in nodes
    ):
        report.error(where, "command.json: у команды нет триггера")
    if not isinstance(edges, list) or len(edges) > 1000:
        report.error(where, "command.json: связей не больше 1000")
    plugins = doc.get("plugins", [])
    if not isinstance(plugins, list) or not all(isinstance(p, str) for p in plugins):
        report.error(where, "command.json: plugins — список id плагинов")


def check_plugin(folder: Path, manifest: dict[str, Any], report: Report, where: str) -> None:
    if manifest.get("id") != folder.name:
        report.error(where, "id в manifest.json не совпадает с именем папки")
    if not isinstance(manifest.get("api_version"), int) or manifest["api_version"] < 1:
        report.error(where, "api_version: целое число от 1")
    permissions = manifest.get("permissions", [])
    if not isinstance(permissions, list) or any(p not in PERMISSIONS for p in permissions):
        report.error(where, f"permissions: только {', '.join(PERMISSIONS)}")
    entry = str(manifest.get("entry", "main.py"))
    if not entry.endswith(".py") or ".." in entry or not (folder / entry).is_file():
        report.error(where, f"entry: нет файла {entry}")
    icon = manifest.get("icon")
    if icon is not None:
        path = folder / str(icon)
        if ".." in str(icon) or not path.is_file() or path.stat().st_size > ICON_MAX:
            report.error(where, "icon: файл иконки в папке плагина, до 128 КБ")


def scan_python(path: Path, report: Report, where: str) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.name)
    except (SyntaxError, UnicodeDecodeError) as err:
        report.error(where, f"{path.name}: не разбирается как Python ({err})")
        return
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names} & RISKY_MODULES
        elif isinstance(node, ast.ImportFrom) and node.module:
            found |= {node.module.split(".")[0]} & RISKY_MODULES
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in RISKY_CALLS:
                found.add(f"{name}()")
    if found:
        report.warn(where, f"{path.name}: проверьте вручную — {', '.join(sorted(found))}")


def _image_ok(path: Path) -> bool:
    head = path.read_bytes()[:12]
    magic = IMAGE_MAGIC.get(path.suffix.lower(), ())
    return any(head.startswith(m) for m in magic) and (
        path.suffix.lower() != ".webp" or head[8:12] == b"WEBP"
    )


def check_files(
    item_type: str, folder: Path, files: list[Path], report: Report, where: str
) -> None:
    total = 0
    for path in files:
        rel = path.relative_to(folder).as_posix()
        size = path.stat().st_size
        total += size
        parts = rel.split("/")
        if any(p.startswith(".") or p == "__pycache__" for p in parts):
            report.error(where, f"{rel}: скрытые и служебные файлы не публикуются")
            continue
        suffix = path.suffix.lower()
        if parts[0] == "screenshots":
            if len(parts) != 2 or suffix not in IMAGE_EXT or size > SCREENSHOT_MAX:
                report.error(where, f"{rel}: скриншоты — png/jpg/webp до 1 МБ")
            elif not _image_ok(path):
                report.error(where, f"{rel}: файл не похож на картинку")
            continue
        if item_type != "plugin":
            if rel not in COMMON_FILES | {PAYLOAD[item_type]}:
                report.error(where, f"{rel}: лишний файл")
            continue
        if suffix not in PLUGIN_EXT:
            report.error(where, f"{rel}: такие файлы в плагине запрещены (только код и данные)")
            continue
        if suffix not in IMAGE_EXT and path.read_bytes()[:4].startswith(BINARY_MAGIC):
            report.error(where, f"{rel}: похоже на исполняемый файл или архив")
        if suffix == ".py":
            scan_python(path, report, where)
    if len(files) > MAX_FILES:
        report.error(where, f"файлов больше {MAX_FILES}")
    if total > SIZE_LIMITS[item_type]:
        report.error(where, f"больше {SIZE_LIMITS[item_type] // MB} МБ")
    shots = [f for f in files if f.relative_to(folder).parts[0] == "screenshots"]
    if len(shots) > MAX_SCREENSHOTS:
        report.error(where, f"скриншотов больше {MAX_SCREENSHOTS}")


def check_extras(item: Item, report: Report, where: str) -> None:
    preview = item.folder / "preview.png"
    if not preview.is_file():
        if item.type == "theme":
            report.error(where, "у темы нужен preview.png (Astra делает его сама при «Поделиться»)")
    elif preview.stat().st_size > PREVIEW_MAX or not _image_ok(preview):
        report.error(where, "preview.png: картинка PNG до 512 КБ")
    changelog = item.folder / "CHANGELOG.md"
    if not changelog.is_file() or changelog.stat().st_size > CHANGELOG_MAX:
        report.error(where, "нужен CHANGELOG.md до 64 КБ")
        return
    try:
        text = changelog.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        report.error(where, "CHANGELOG.md: нужна кодировка UTF-8")
        return
    version = str(item.manifest.get("version", ""))
    if version and version not in text:
        report.warn(where, f"в CHANGELOG.md нет записи о версии {version}")


def load_item(folder: Path, item_type: str, report: Report) -> Item | None:
    where = folder.as_posix()
    pattern = PLUGIN_ID_RE if item_type == "plugin" else ID_RE
    if not pattern.match(folder.name):
        report.error(where, "имя папки (id): латиница, цифры и «-», с буквы")
        return None
    if any(p.is_symlink() for p in folder.rglob("*")):
        report.error(where, "ссылки (symlink) запрещены")
        return None
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    manifest = read_json(folder / "manifest.json", MANIFEST_MAX, report, where)
    if manifest is None:
        return None
    errors = len(report.errors)
    check_manifest(item_type, manifest, report, where)
    payload = None
    if item_type == "plugin":
        check_plugin(folder, manifest, report, where)
    else:
        payload = read_json(folder / PAYLOAD[item_type], 256 * 1024, report, where)
        if payload is not None and item_type == "theme":
            check_theme(payload, report, where)
        elif payload is not None:
            check_command(payload, report, where)
    check_files(item_type, folder, files, report, where)
    item = Item(item_type, folder.name, folder, manifest, payload, files)
    check_extras(item, report, where)
    return item if len(report.errors) == errors else None


def load_catalog(root: Path, report: Report) -> list[Item]:
    items: list[Item] = []
    base = root / "items"
    if not base.is_dir():
        report.error("items", "нет папки items")
        return items
    for child in sorted(base.iterdir()):
        if child.name not in TYPES:
            report.error(child.as_posix(), f"неизвестный раздел — только {', '.join(TYPES)}")
            continue
        for folder in sorted(p for p in child.iterdir() if p.is_dir()):
            item = load_item(folder, TYPES[child.name], report)
            if item is not None:
                items.append(item)
    plugin_ids = {i.id for i in items if i.type == "plugin"}
    for item in items:
        if item.type == "command" and item.payload:
            missing = [p for p in item.payload.get("plugins", []) if p not in plugin_ids]
            if missing:
                report.warn(item.folder.as_posix(), f"нужны плагины не из каталога: {missing}")
    return items


def load_featured(root: Path, items: list[Item], report: Report) -> set[str]:
    path = root / "featured.json"
    if not path.is_file():
        return set()
    data = read_json(path, MANIFEST_MAX, report, "featured.json")
    keys = data.get("featured") if data else None
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        report.error("featured.json", 'нужно {"featured": ["themes/<id>", …]}')
        return set()
    known = {f"{folder}/{i.id}" for i in items for folder, t in TYPES.items() if t == i.type}
    for key in keys:
        if key not in known:
            report.warn("featured.json", f"{key}: такого элемента нет")
    return set(keys) & known
