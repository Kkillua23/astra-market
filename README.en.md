# Astra Market — a catalog of themes, commands and plugins

[Русский](README.md)

A catalog repository for [Astra](https://github.com/Kkillua23/astra). There is no server:
GitHub stores the files, GitHub Actions checks pull requests and builds `index.json`, and Astra
downloads the catalog straight from `raw.githubusercontent.com`.

## Layout

```
items/
  themes/<id>/      manifest.json, theme.json, preview.png, CHANGELOG.md, screenshots/*
  commands/<id>/    manifest.json, command.json, preview.png*, CHANGELOG.md, screenshots/*
  plugins/<id>/     manifest.json (the plugin manifest), main.py, …, preview.png*, CHANGELOG.md
featured.json       “Featured” — edited by the catalog owner only
scripts/market.py   validation and build (Python standard library only)
```

`*` — optional. After a merge into `main`, the “Публикация каталога” (publish) workflow builds a
zip for every item plus `index.json` (sha256, sizes, file links) and pushes them to the `catalog`
branch.

## Your own catalog in 5 minutes

1. Click **Use this template → Create a new repository** (public).
2. **Settings → Actions → General → Workflow permissions → Read and write permissions** so the
   workflow can update the `catalog` branch.
3. **Actions → Публикация каталога → Run workflow** (afterwards it runs after every merge).
4. In Astra: **Market → ⚙ → Catalog address** —
   `https://raw.githubusercontent.com/<you>/<repo>/catalog/index.json`.

Delete the examples in `items/` or keep them.

## Publishing a theme, command or plugin

The easy way is from Astra: pick **“Share”** on your theme, command or plugin. Astra builds the
`items/<type>/<id>/` folder with a manifest (and renders `preview.png` for themes) and shows the
steps:

1. **Fork** this repository.
2. In your fork: **Add file → Upload files** and drop the exported `items` folder.
3. Choose **Create a new branch** → **Propose changes** → **Create pull request**.
4. Wait for the green check. The catalog owner reviews and merges the PR.

Updates work the same way with a higher `version` and a `CHANGELOG.md` entry. After the merge,
everyone who installed the item sees “Update” in the Market.

## Rules

- **manifest.json:** `id` = folder name (latin letters, digits, `-`), `name` and `description` in
  `ru` and `en`, `author`, `version` (`1.2.3`), optional `tags` (up to 5), `min_app_version`,
  `homepage` (https). No `featured` in manifests — the owner sets it in `featured.json`.
- **Sizes:** themes and commands up to 2 MB, plugins up to 5 MB and 200 files; `preview.png` up to
  512 KB, screenshots (`screenshots/`, png/jpg/webp) up to 6 × 1 MB; `CHANGELOG.md` is required.
- **Plugins:** Python code and data only (`.py .json .md .txt .csv .toml .yaml .ini`, images,
  `.wav .mp3 .ogg`). No `.exe`, `.dll`, `.pyd`, `.bat`, `.ps1`, archives or hidden files. Network,
  files and PowerShell go through `astra_sdk` and the declared `permissions`, so Astra asks the
  user. Imports like `subprocess`, `ctypes`, `socket`, `urllib` are flagged for manual review.
- **Themes:** `theme.json` is a theme exported from Astra. **Commands:** `command.json` is an
  exported command (`"format": "astra-command"`); required plugins are listed in `plugins`.
- Changed an item's files? Bump `version`, or the check fails.
- Only your own work or work you may publish. Nothing malicious or inappropriate.

## Local check

```
python scripts/market.py validate
python scripts/market.py build --out public --base-url http://127.0.0.1:8000/
python -m http.server 8000 --directory public
```

You can point Astra at `http://127.0.0.1:8000/index.json` to test (plain http is allowed only for
127.0.0.1 and localhost).

## Reports

Each item page in Astra has **“Report”**, which opens an issue from the template. The owner
removes the item from `items/`, and after publishing it disappears from the Market.
