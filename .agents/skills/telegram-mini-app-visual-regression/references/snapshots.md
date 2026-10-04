# Эталоны и детерминированные снимки

Playwright snapshots зависят от браузера и ОС. Создавай и сравнивай baseline в сопоставимой среде; записывай установленную версию runner/browser. У проекта могут быть разные эталоны для разных сред.

## Пример для существующего Playwright Test проекта

Адаптируй route и fixture под приложение; это пример теста, не готовая интеграция в любой проект:

```typescript
import { test, expect } from '@playwright/test';

for (const width of [390, 820, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`checkout ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      // Dev-only route подключает явный fake bridge и фиксированные данные.
      await page.goto(`/visual-fixtures/checkout?theme=${theme}&locale=ru`);
      await expect(page.getByRole('heading', { name: 'Подтверждение' })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect(page).toHaveScreenshot(`checkout-${width}-${theme}.png`, {
        animations: 'disabled',
      });
    });
  }
}
```

`colorScheme` меняет browser media query, но не создает Telegram themeParams: fake adapter должен передать тему отдельно. URL fixture не должен давать обход auth в production. Для динамического сценария контролируй API и clock; `networkidle` и произвольный sleep не определяют готовность приложения.

## Разбор diff

Отделяй ожидаемые изменения от дефектов: шрифт, перенос строки, перекрытие, отступ, контраст/тема, исчезнувшее действие. Сначала проверь fixture и среду, затем код. Не маскируй весь экран из-за одного динамического значения.

Baseline хранится рядом с тестами по правилам runner и обновляется вместе с осмысленным описанием изменения. Временная демонстрация дефекта не входит в целевой продукт.

В изолированной forward-пробе временный baseline может выбрать и визуально просмотреть автор пробы, явно записав это в отчет. Для продукта используй уже принятый процесс review дизайна/изменений; слово «согласование» само по себе не вводит дополнительный запрос разрешения пользователю. В обоих случаях actual не принимается эталоном без просмотра.

Источники сверены 3 октября 2026 года: [Playwright snapshots](https://playwright.dev/docs/test-snapshots), [эмуляция](https://playwright.dev/docs/emulation). Матрица из примера — критерий этой пробы, а не обещание поддержки устройств.
