# Локальные замеры скорости и памяти

`tools/local-performance/run.mjs` измеряет установленную библиотеку 0.28.0 и
скомпилированные композиции из отдельного consumer. Это лабораторный профиль
Chrome на текущем ПК. Реальные Telegram WebView, слабое устройство, production
backend и целевые Android/iOS он не подтверждает. Пункт 069 сохраняет отдельное
условие проверки бюджетов на целевых устройствах.

## Подготовить воспроизводимый профиль

Сначала выполните [проверку поставки](distribution-contract.md) с браузером.
Нужны сохраненный `distribution-report.json`, соответствующая запись приемки,
точный npm tarball и сохранившийся установленный UI consumer из этого отчета.
Helper проверяет SHA-256 отчета и tarball, версию установленного пакета, затем
побайтово сравнивает каждый исполняемый файл и CSS установленной библиотеки с
содержимым принятого tarball. Скомпилированные `main.js` и `screens.js` — отдельная
fixture consumer; их хеши записываются отдельно от библиотечного архива.
Runtime из исходного checkout не обслуживается. При очистке временного consumer
нужна новая проверка поставки; исчезнувший путь нельзя заменить исходниками.

После `npm.cmd ci` в корне создайте JSON-конфигурацию с путями своей приемки:

```json
{
  "distributionReport": "C:/owned-evidence/distribution-report.json",
  "acceptance": "C:/owned-evidence/local-028-acceptance.json",
  "tarball": "C:/owned-evidence/awesome-telegram-patterns-0.28.0.tgz",
  "output": "C:/owned-evidence/local-performance-run-01",
  "samples": 7,
  "largeItems": 500,
  "cycles": 100,
  "delayMs": 150
}
```

```powershell
$env:CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
node tools/local-performance/run.mjs C:/owned-evidence/configuration.json
```

В Linux/macOS используйте `npm ci`, доступный Chrome и собственные абсолютные
пути. Output должен отсутствовать; существующий каталог и symlink/junction
отклоняются, файлы владельца сохраняются. Helper не устанавливает зависимости,
не загружает `.env` и не принимает реальные токены, URL backend или команду оплаты.
HTTP fixture слушает только loopback; браузер блокирует запросы к другим origins.
Это контроль тестовой среды, а не OS sandbox для произвольного недоверенного кода.

## Что измеряется

| Путь | Наблюдение и границы |
| --- | --- |
| Загрузка шести композиций | Несколько новых browser contexts, HTTP `no-store`, navigation/resource timings и время наблюдения всех `ready` состояний. Polling наблюдателя входит в результат; это не LCP. |
| Крупный список | Фиксированный синтетический набор с записанным SHA-256, фактически отрисованные строки и DOM-узлы, время до двух animation frames после готовности. Данные мгновенно передает локальный service; серверная загрузка сюда не приписывается. |
| Взаимодействие | Настоящий pointer click по последнему элементу; проверяется выбранный ID. Время от `pointerdown` до двух кадров сохраняется отдельно от `locator.click`/ожиданий автоматизации; это не INP. |
| Сетевой путь | Реальный loopback HTTP с явной задержкой, ограниченный timeout, error/retry вместо вечного spinner и завершение dispose даже для loader, игнорирующего abort. Задержка искусственная, production latency не измеряется. |
| Потерянный ответ записи | Сервер применяет эффект один раз по стабильному operation ID и неизменному payload, затем обрывает ответ. Клиент сохраняет `unknown`, повторно открывает указатель и сверяет один эффект через GET. Новая прикладная запись не отправляется. |
| Память и повторные входы | После прогрева — серии mount/dispose, принудительный GC, `JSHeapUsedSize`, `JSHeapTotalSize`, `Nodes`, `Documents`, `JSEventListeners`. Намеренно удержанные живые экраны служат положительным контролем чувствительности измерителя, затем удаляются. |
| Background/resume | Отдельный собственный Chrome с новым профилем подключается через `connectOverCDP(..., {noDefaults:true})`. Переключаются две собственные вкладки; записываются настоящие `visibilitychange`/`freeze`/`resume`, их `isTrusted` и сохранность поля. Принятие команды без событий получает `not-observed`, а не PASS. Синтетические DOM-события вместо них не отправляются. |

HTTP-запрос и прикладной эффект различаются. В сохраненном первом прогоне Chrome
повторил один `fetch` POST шесть раз после обрыва соединения. Исходная fixture ошибочно
считала каждый запрос новым эффектом и провалила проверку. Исправлена только fixture:
серверная идемпотентность по ID/payload; число транспортных попыток остается в отчете.
Один вызов `ApiClient` не обещает один HTTP-запрос во всех браузерах и proxy.

В `report.json` сохраняются все samples, профиль, данные, хеши assets/помощников,
запросы и незавершенные условия. Heap после GC — JS heap renderer, а не RSS всего
процесса, native/GPU память или системный предел. Разброс heap/числа узлов и конечная
серия с очищенными listeners не доказывают отсутствие всех возможных утечек.

## Предварительный бюджет из данных

Для каждого времени helper сохраняет минимум, медиану, максимум и медианное
абсолютное отклонение (MAD). Локальный порог вычисляется по открытому правилу:
`observed maximum + 3 × MAD`. Это инженерный ориентир для повторного прогона того же
профиля, а не статистическая доверительная граница, продуктовый SLA или полевой
percentile. Он не заменяет исходные samples и согласование целевых устройств.

Запустите второй профиль с теми же параметрами и новым output. Сравнение повторов:

```powershell
node tools/local-performance/compare.mjs C:/owned-evidence/run-01/report.json C:/owned-evidence/run-02/report.json C:/owned-evidence/holdout.json
```

Сравнение требует одинаковых artifacts, данных, версий и профиля; файл результата
должен отсутствовать. Это проверка повторяемости одного артефакта. Смена приложения,
устройства или единственного исследуемого фактора требует отдельного рассмотрения
происхождения, а не удаления проверки равенства. Превышение сохраняется как FAIL;
порог нельзя задним числом поднять для сокрытия результата. Один удачный повтор не
валидирует бюджет для остальных ПК и WebView.

Exit 0 измерителя означает прохождение всех заявленных локальных условий;
exit 1 сохраняет провал/неполное условие, exit 2 — отказ конфигурации/операции.
`measurements_completed:true` означает наличие полного набора измерений, но при
неподтвержденном lifecycle `passed` остается false. Сравнение времен независимо
сохраняет `full_fixture_passed` и всегда `production_ready:false`.

В первоначальных полных прогонах Chrome 156 команды lifecycle не дали событий
`freeze`/`resume`: поле сохранилось, но сценарий остался непринятым. Отдельный
аудит установил влияние эмуляции фокуса Playwright: удаление фоновых launch flags
не помогло, а `noDefaults:true` в новом собственном default context дало настоящие
trusted-события. В той же CDP-сессии включение эмуляции фокуса повторило проблему,
выключение вернуло события. Отключение во второй сессии не снимает исходный захват.

Измеритель теперь использует этот отдельный профиль только для lifecycle; его
process и каталог удаляются после проверки. Нужен явный `CHROME_PATH`. Существующий
браузер пользователя не подключается. Для повторения только исправленной стадии
используйте прежнюю конфигурацию с новым output:

```powershell
node tools/local-performance/lifecycle.mjs C:/owned-evidence/lifecycle-configuration.json
```

Точечный повтор на тех же принятых assets прошел с настоящими событиями и
сохраненным полем. Старые полные отчеты не меняются: их `passed:false` остается
историческим результатом, а исправленная стадия привязывается отдельным отчетом.
Это локальная проверка Chrome, не OS background/resume телефона и не Telegram.
Текущий runbook сам не назначает пункты 069/070 завершенными.

## Проверить сам helper

```powershell
node --test tools/local-performance/check.test.mjs
python -m unittest discover -s tests -p test_local_performance.py -v
```

Проверяются реальное создание результата сравнения, отказ при изменении профиля,
измеримое превышение порога, некорректные samples, повторная запись и junction.
Эти проверки сами не запускают Chrome и не заменяют измерения installed consumer.

Источники механизмов: [CDP Performance](https://chromedevtools.github.io/devtools-protocol/tot/Performance/),
[HeapProfiler](https://chromedevtools.github.io/devtools-protocol/tot/HeapProfiler/),
[Page lifecycle](https://chromedevtools.github.io/devtools-protocol/tot/Page/),
[Chrome focus emulation и visibility](https://developer.chrome.com/docs/devtools/rendering/apply-effects),
[Playwright connectOverCDP/noDefaults](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp-option-no-defaults).
Проверено 6 ноября 2026 на локальном Chrome 156; это не обещание поддержки
экспериментальных CDP-команд каждым Telegram-клиентом.
