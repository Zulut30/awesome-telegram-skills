# Я работаю с ИИ-агентом

Цель за 10 минут: подключить нужные скиллы к своему проекту и получить от агента решение, проверенное по правилам Telegram. Подходят Codex, Claude Code, GitHub Copilot, Cursor и другие агенты с поддержкой формата Agent Skills.

## 1. Установите скиллы в проект

Из клона репозитория (сначала `--dry-run`, затем без него):

```bash
python3 scripts/install_skills.py --project ~/projects/my-bot --skill telegram-bot-python --skill telegram-code-patterns --dry-run
```

```powershell
python scripts/install_skills.py --project "C:\projects\my-bot" --skill telegram-bot-python --skill telegram-code-patterns --dry-run
```

Скиллы копируются в `.agents/skills/` проекта — этот каталог читают Codex и GitHub Copilot. Claude Code читает только `.claude/skills/`: добавьте к команде `--agent claude`. Каждый скилл самостоятелен: берите только нужные.

## 2. Попросите агента

```text
$telegram-bot-python Добавь в мой бот на aiogram меню из двух кнопок и проверь его без сети.
$telegram-mini-app-auth Проверь initData на backend и создай сессию.
$telegram-payments Подключи оплату Stars с выдачей доступа только после successful_payment.
```

В Claude Code скилл вызывается как `/telegram-bot-python`. Если агент не видит скилл, проверьте, что каталог лежит в `.claude/skills/`, и перезапустите агента в каталоге проекта.

## 3. Проверьте результат

Попросите агента назвать выбранный API, версию библиотеки, измененные файлы и выполненные проверки. Решения о правах, оплате и хранении данных остаются за вами: скилл подсказывает, как их проверить.

## Что дальше

- Какой скилл для какой задачи — [каталог скиллов](../../README.md#skills).
- Правила для самого агента при подключении библиотеки — [docs/for-agents.md](../for-agents.md).
