"""Каталог Astra Market: проверка элементов и сборка index.json с zip-пакетами.

    python scripts/market.py validate [--base-ref origin/main]
    python scripts/market.py build --out public [--base-url URL] [--repository URL]

Только стандартная библиотека Python 3.11+. Правила — в market_rules.py.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from market_rules import TYPES, Item, Report, load_catalog, load_featured, parse_version

ROOT = Path(__file__).resolve().parent.parent
FORMAT = "astra-market"
SCHEMA = 1
# В пакет не идёт то, что каталог отдаёт отдельными файлами.
NOT_PACKED = {"preview.png", "README.md"}
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def _rel(item: Item) -> str:
    folder = next(k for k, v in TYPES.items() if v == item.type)
    return f"items/{folder}/{item.id}"


def check_versions(root: Path, items: list[Item], base_ref: str, report: Report) -> None:
    """Изменённый элемент обязан поднять version — иначе приложения не увидят обновление."""
    for item in items:
        old_raw = _git(root, "show", f"{base_ref}:{_rel(item)}/manifest.json")
        if old_raw is None:
            continue  # новый элемент
        changed = _git(root, "diff", "--name-only", base_ref, "--", _rel(item))
        if not changed or not changed.strip():
            continue
        try:
            old = str(json.loads(old_raw).get("version", "0.0.0"))
            if parse_version(str(item.manifest["version"])) <= parse_version(old):
                report.error(_rel(item), f"файлы изменились — поднимите version (было {old})")
        except (ValueError, KeyError):
            continue


def print_report(report: Report, items: list[Item]) -> None:
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    for where, text in report.errors:
        print(f"::error file={where}::{text}" if github else f"ОШИБКА  {where}: {text}")
    for where, text in report.warnings:
        print(f"::warning file={where}::{text}" if github else f"ВНИМАНИЕ {where}: {text}")
    print(
        f"Элементов: {len(items)}, ошибок: {len(report.errors)}, предупреждений: "
        f"{len(report.warnings)}"
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    lines = ["## Проверка каталога", "", "| Тип | id | Версия | Автор |", "|---|---|---|---|"]
    lines += [
        f"| {i.type} | {i.id} | {i.manifest['version']} | {i.manifest['author']} |" for i in items
    ]
    if report.errors:
        lines += ["", "### Ошибки", *(f"- `{w}`: {t}" for w, t in report.errors)]
    if report.warnings:
        lines += ["", "### Посмотреть глазами", *(f"- `{w}`: {t}" for w, t in report.warnings)]
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _file_entry(data: bytes, rel: str, base_url: str) -> dict[str, Any]:
    return {"url": base_url + rel, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _zip(item: Item) -> bytes:
    """Детерминированный zip: те же файлы — тот же sha256 при каждой сборке."""
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in item.files:
            rel = path.relative_to(item.folder).as_posix()
            if rel in NOT_PACKED or rel.startswith("screenshots/"):
                continue
            info = zipfile.ZipInfo(rel, ZIP_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def _dates(root: Path, item: Item) -> tuple[str, str]:
    """Когда элемент появился и когда менялся — по истории git (без неё — сегодня)."""
    log = (_git(root, "log", "--format=%cs", "--", _rel(item)) or "").split()
    today = date.today().isoformat()
    return (log[-1] if log else today), (log[0] if log else today)


def _publish(out: Path, rel: str, data: bytes, base_url: str) -> dict[str, Any]:
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return _file_entry(data, rel, base_url)


def build_item(
    root: Path, item: Item, out: Path, base_url: str, featured: set[str]
) -> dict[str, Any]:
    m = item.manifest
    folder = next(k for k, v in TYPES.items() if v == item.type)
    files = f"files/{folder}/{item.id}"
    added, updated = _dates(root, item)
    entry: dict[str, Any] = {
        "type": item.type,
        "id": item.id,
        "name": m["name"],
        "description": m["description"],
        "author": m["author"].strip(),
        "version": m["version"],
        "tags": m.get("tags", []),
        "featured": f"{folder}/{item.id}" in featured,
        "min_app_version": m.get("min_app_version", "0.0.0"),
        "homepage": m.get("homepage"),
        "added_at": added,
        "updated_at": updated,
        "permissions": m.get("permissions", []) if item.type == "plugin" else [],
        "requires": (item.payload or {}).get("plugins", []) if item.type == "command" else [],
        "package": _publish(
            out, f"packages/{folder}/{item.id}-{m['version']}.zip", _zip(item), base_url
        ),
        "preview": None,
        "icon": None,
        "symbol": None,
        "screenshots": [],
        "changelog": _publish(
            out, f"{files}/CHANGELOG.md", (item.folder / "CHANGELOG.md").read_bytes(), base_url
        ),
    }
    preview = item.folder / "preview.png"
    if preview.is_file():
        entry["preview"] = _publish(out, f"{files}/preview.png", preview.read_bytes(), base_url)
    for shot in sorted((item.folder / "screenshots").glob("*")):
        data = shot.read_bytes()
        entry["screenshots"].append(
            _publish(out, f"{files}/screenshots/{shot.name}", data, base_url)
        )
    if item.type == "plugin" and m.get("icon"):
        icon = item.folder / str(m["icon"])
        entry["icon"] = _publish(out, f"{files}/{icon.name}", icon.read_bytes(), base_url)
    if item.type == "command" and item.payload:
        entry["symbol"] = item.payload["command"].get("icon")
    if item.type == "theme" and item.payload:
        entry["appearance"] = item.payload.get("appearance")
        entry["accent"] = item.payload.get("accent")
    return entry


def build(root: Path, out: Path, base_url: str, repository: str) -> int:
    report = Report()
    items = load_catalog(root, report)
    featured = load_featured(root, items, report)
    print_report(report, items)
    if report.errors:
        return 1
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    index = {
        "format": FORMAT,
        "schema": SCHEMA,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "repository": repository,
        "items": [build_item(root, item, out, base_url, featured) for item in items],
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), "utf-8")
    print(f"Собрано: {out / 'index.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Каталог Astra Market")
    parser.add_argument("--root", default=str(ROOT), help="папка каталога (где items/)")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="проверить элементы")
    check.add_argument("--base-ref", help="ветка, с которой сравнить версии (для PR)")
    make = sub.add_parser("build", help="собрать index.json и zip")
    make.add_argument("--out", default="public")
    make.add_argument("--base-url", default="", help="префикс ссылок, напр. raw.githubusercontent")
    make.add_argument("--repository", default="", help="https://github.com/<owner>/<repo>")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "build":
        base = args.base_url.rstrip("/") + "/" if args.base_url else ""
        return build(root, Path(args.out).resolve(), base, args.repository)
    report = Report()
    items = load_catalog(root, report)
    load_featured(root, items, report)
    if args.base_ref:
        check_versions(root, items, args.base_ref, report)
    print_report(report, items)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
