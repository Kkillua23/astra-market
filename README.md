# Astra Market — каталог тем, команд и плагинов

[English](README.en.md)

Это репозиторий-каталог для [Astra](https://github.com/Kkillua23/astra). Своего сервера нет:
GitHub хранит файлы, GitHub Actions проверяет пулл-реквесты и собирает `index.json`,
а Astra скачивает каталог напрямую с `raw.githubusercontent.com`.

## Как устроено

```
items/
  themes/<id>/      manifest.json, theme.json, preview.png, CHANGELOG.md, screenshots/*
  commands/<id>/    manifest.json, command.json, preview.png*, CHANGELOG.md, screenshots/*
  plugins/<id>/     manifest.json (манифест плагина), main.py, …, preview.png*, CHANGELOG.md
featured.json       «Рекомендуемые» — правит только владелец каталога
scripts/market.py   проверка и сборка (только стандартная библиотека Python)
```

`*` — по желанию. После слияния в `main` Action «Публикация каталога» собирает zip каждого
элемента и `index.json` (sha256, размеры, ссылки на файлы) и кладёт их в ветку `catalog`.

## Свой каталог за 5 минут

1. Нажмите **Use this template → Create a new repository** (публичный).
2. **Settings → Actions → General → Workflow permissions → Read and write permissions** — чтобы
   Action мог обновлять ветку `catalog`.
3. **Actions → Публикация каталога → Run workflow** (дальше он запускается сам после каждого слияния).
4. В Astra: **Маркет → ⚙ → Адрес каталога** —
   `https://raw.githubusercontent.com/<вы>/<репозиторий>/catalog/index.json`.

Примеры в `items/` можно удалить или оставить.

## Как опубликовать тему, команду или плагин

Проще всего — из Astra: у своей темы, команды или плагина выберите **«Поделиться»**. Astra
соберёт папку `items/<тип>/<id>/` с манифестом (для тем сама нарисует `preview.png`) и покажет
шаги. Коротко:

1. Сделайте **Fork** этого репозитория.
2. В своём форке: **Add file → Upload files** и перетащите папку `items` из экспорта.
3. Внизу выберите **Create a new branch** → **Propose changes** → **Create pull request**.
4. Дождитесь зелёной проверки. Владелец каталога посмотрит и примет PR.

Обновление — то же самое, но с большей `version` и записью в `CHANGELOG.md`. После слияния
у всех, кто поставил элемент, в Маркете появится «Обновить».

## Правила

- **manifest.json:** `id` = имя папки (латиница, цифры, `-`), `name` и `description` на `ru` и `en`,
  `author`, `version` (`1.2.3`), по желанию `tags` (до 5), `min_app_version`, `homepage` (https).
  `featured` в манифесте нельзя — «Рекомендуемые» задаёт владелец в `featured.json`.
- **Размеры:** тема и команда — до 2 МБ, плагин — до 5 МБ и 200 файлов; `preview.png` — до 512 КБ,
  скриншоты (`screenshots/`, png/jpg/webp) — до 6 штук по 1 МБ; `CHANGELOG.md` обязателен.
- **Плагины:** только код Python и данные (`.py .json .md .txt .csv .toml .yaml .ini`, картинки,
  `.wav .mp3 .ogg`). Никаких `.exe`, `.dll`, `.pyd`, `.bat`, `.ps1`, архивов и скрытых файлов.
  Сеть, файлы, PowerShell — только через `astra_sdk` и объявленные `permissions`: тогда Astra
  спросит пользователя. Импорт `subprocess`, `ctypes`, `socket`, `urllib` и т. п. проверка
  помечает для ручного просмотра.
- **Темы:** `theme.json` — файл экспорта темы из Astra. **Команды:** `command.json` — экспорт
  команды (`"format": "astra-command"`); нужные плагины перечислены в `plugins`.
- Изменили файлы элемента — поднимите `version`, иначе проверка не пройдёт.
- Только свои работы или то, что вы вправе публиковать. Без вредоносного и неприемлемого.

## Проверить локально

```
python scripts/market.py validate
python scripts/market.py build --out public --base-url http://127.0.0.1:8000/
python -m http.server 8000 --directory public
```

Адрес `http://127.0.0.1:8000/index.json` можно указать в Astra для проверки (http — только для
127.0.0.1 и localhost).

## Жалобы

В Astra на странице элемента есть **«Пожаловаться»** — он открывает issue по шаблону. Владелец
каталога удаляет элемент из `items/`, и после публикации он пропадает из Маркета.
