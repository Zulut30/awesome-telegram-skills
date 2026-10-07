# Зрелость компонентов и способ проверки

Доступно с 0.6.0, проверено на 0.24.0.

Начиная с 0.6.0, каждый компонент в `components.json` и каждый рецепт имеют `maturity`. Для импортов группы действует ее статус; отдельный символ не получает более сильной гарантии по факту экспорта. Проверяйте каталог установленной версии: статус не переносится автоматически с другой версии.

- `stable`: определен стабильный контракт, выполнены необходимые проверки его scope и заданы правила совместимости.
- `experimental`: API/сценарий реализован, но стабильность и все условия приемки еще не заявлены. Подключайте с учетом границ и проверками проекта.
- `reference`: справочный запрос/фрагмент требует конкретных параметров, контекста и прикладного workflow. Не выдавайте его за законченную функциональность.

Это независимо от `verification`: `sdk` означает построение объекта, `mock` — synthetic execution, `browser` — конкретную браузерную проверку, `live` — подтвержденный сценарий настоящего Telegram, `not_run` — отсутствие исполнения. Live само по себе не присваивает stable, а стабильный request builder не обещает весь платежный workflow.

В поставке 0.24.0: 47 групп experimental; 31 рецепт experimental, 284 reference; stable/live пока не заявлены. При выборе посмотрите `scope` и обязанности host: права, состояние и восстановление могут требовать прикладной реализации.

```python
from telegram_patterns import RecipeCatalog

catalog = RecipeCatalog()
assert catalog.get("two-columns").maturity == "experimental"
assert catalog.get("api.sendPhoto").maturity == "reference"
assert catalog.search(maturity="stable") == ()
assert catalog.search("две кнопки", maturity="experimental")[0].id == "two-columns"
```

CLI: `telegram-patterns recipes --maturity experimental`; галерея имеет отдельные фильтры зрелости и проверки. Поиск не выполняет код. Старые records schema 1 без maturity принимаются с conservative default, никогда stable.
