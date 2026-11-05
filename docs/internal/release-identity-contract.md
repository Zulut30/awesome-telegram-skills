# Общая identity numeric и RC выпуска

Подготовка пункта 099 от 5 ноября 2026. `scripts/release_identity.py` — небольшой stdlib-only контракт существующего release pipeline. Он не изменяет manifests и сам не принимает production/RC критерии. Подключены builder/SBOM, distribution contract, device/live reports, changelog и release/publish workflows. Эта интеграция не создает RC, тег или публикацию; внешняя приемка остается обязательной.

## Поддерживаемый формат

| Release | Python manifest / wheel version | npm manifest / общая identity | Git tag |
| --- | --- | --- | --- |
| numeric | `0.24.0` | `0.24.0` | `v0.24.0` |
| candidate | `1.0.0rc1` | `1.0.0-rc.1` | `v1.0.0-rc.1` |
| candidate zero | `1.0.0rc0` | `1.0.0-rc.0` | `v1.0.0-rc.0` |

Это намеренно более узкий набор, чем полные PEP 440/SemVer: ровно три release-компонента, optional `rcN` либо `-rc.N`, ASCII digits, без leading zero кроме самого `0`. Значения — exact Python `int` в диапазоне `0..9007199254740991`, включая RC number; `bool`, float, отрицательные и overflow запрещены даже при прямом создании dataclass. Верхняя граница общего контракта обеспечивает безопасное представление чисел в JavaScript; это собственное ограничение проекта, а не общий предел PEP 440/SemVer.

Epoch/post/dev/local/build metadata, alpha/beta, implicit RC number, alternate PEP spellings/separators, whitespace и `v` внутри version отказываются явно. Их нельзя автоматически обрезать или превращать в final. Входной parser допускает обе canonical registry forms; manifest reader требует конкретную форму своего registry.

## API

`ReleaseIdentity(major, minor, patch, rc=None)` — frozen dataclass, сравнение equality по всей identity. Properties:

- `release`: `(major, minor, patch)` для явно заданного base threshold; это не сравнение RC с final.
- `base_version`, `python_version`, `npm_version`, `identity`, `tag`, `is_prerelease`.
- `precedence_key`: ключ для `sorted(..., key=lambda r: r.precedence_key)`; RC сравнивается численно, например `rc.2 < rc.10 < final < next-base-rc.0`. Сам dataclass не дает неявного ordering.
- `wheel_filename(distribution_name)`: pure Python `py3-none-any` basename без build tag; `Awesome.Telegram--Patterns` → `awesome_telegram_patterns-1.0.0rc1-py3-none-any.whl`.
- `npm_tarball_filename(package_name)`: `@awesome-telegram/patterns` → `awesome-telegram-patterns-1.0.0-rc.1.tgz`; unscoped имя сохраняется. Поддерживаются lowercase ASCII имена с digit/letter в начале каждой части, далее digits/letters/`._-`, длина всего имени до 214. Это безопасный subset package names, не полный registry validator.

Имена wheel distribution и scoped npm package — разные входные типы. Методы не принимают filesystem paths/URLs; `@scope/name` разрешается только npm методу. Wheel name нормализуется по PyPA: runs `-_.` заменяются `_`, uppercase понижается. Версия wheel остается Python canonical RC version; замена `-` на `_` в npm version не является правильной нормализацией версии wheel.

`parse_release_version(text)` возвращает identity из трех поддержанных форм. `parse_release_tag(text)` принимает только `v` + canonical identity: `v1.0.0rc1` отклоняется. `ReleaseIdentityError(ValueError)` различает отказ от успешного parsing; сообщения не являются stable machine-readable codes.

`read_release_identity(pyproject_path, package_json_path)` читает ровно переданные UTF-8 файлы через TOML/JSON parsers. Требует `[project].version` и top-level npm `version`, canonical Python/npm forms и совпадение identity. Не ищет manifests в cwd/git/env, не использует network, не записывает и не исправляет файлы. Ошибки чтения/формата/отсутствующих полей и duplicate JSON keys отклоняются; TOML duplicate keys отклоняет `tomllib`. Пути могут быть абсолютными или относительными к caller cwd, согласно обычному `Path`.

## Интеграция и границы

Не заменять исторические numeric tags и не менять immutability выпущенных версий. Catalog/report directory/release notes используют общую identity, package metadata и filenames — формат конкретного registry. Device/live report thresholds должны явно сравнивать base tuple, чтобы новый RC не обходил требование отчетов. Для exact release acceptance/equality использовать всю identity; `release` не означает passed final.

`is_prerelease` означает наличие RC segment. Политика GitHub «все 0.x releases являются prerelease» остается отдельным условием caller, а не свойством SemVer numeric version. Release workflow оставляет prerelease для 0.x и любого RC; final >=1.0.0 может быть обычным release только после обязательных gates. Registry workflow сохраняет opt-in `PUBLISH_TO_REGISTRIES=true`, OIDC, SHA256SUMS и pinned actions; RC npm получает dist-tag `rc`, numeric использует `latest`. Эти настройки не запускают workflow и не подтверждают доступ к registry.

`build_release.ref_identity(ref, root=None)` сначала разрешает ref в один commit, затем читает **обе** manifests через `git show` этого commit и передает временные копии общему reader. Dirty checkout и более новый HEAD не подменяют исходные версии. `validate_tag(tag, root=None)` требует canonical существующий tag и точное совпадение его identity с обеими committed manifests. Исторический `.github/release-tags.json` не изменен; backfill по-прежнему допускает только numeric entries и проверяет обе версии перед созданием отсутствующего тега.

Builder выбирает wheel/tarball basenames общим helper. SBOM содержит Python `version/purl` с `rcN`, npm — с `-rc.N`; SHA256 привязан к соответствующему artifact. Общие SBOM filename, notes и result version используют canonical identity. Distribution contract проверяет basename, Python `__version__` и METADATA, canonical recipe identity, точные исходные bytes, archive allowlist, RECORD и TypeScript dist bytes. RC не ослабляет source/hash binding; source module `__version__` остается Python form.

Device/live `template`, `new`, `probe` path и `check` нормализуют поддержанный Python-form input в canonical identity. Поле report.release должно точно совпадать с canonical identity: нельзя приложить final отчет к RC или заменить номер candidate. Bundle закрепляет один commit для manifests и report archive. `version_tuple()` сравнивает base tuple для прежнего threshold `(0,25,0)`, сохраняя numeric 0.x policy; RC не может обойти report requirement. Для **любого RC** и **numeric final >=1.0.0** `check`/`bundle` дополнительно требуют все platform/scenario status=`passed`. Оформленные blocked/not-run/failed вызывают отказ до записи release assets; снятие `rc` не снимает production gate. Numeric 0.x сохраняет прежние явно размеченные partial/blocked результаты, которые не являются production приемкой. Templates всегда not-run и без device/live evidence. Missing report завершается ошибкой для любого RC и numeric от 0.25.0; более старый numeric release сохраняет прежний skip.

Artifact existence/hash/content, source commit, полный installed-consumer verifier, реальные device/provider/pilot проверки и решение публикации принимаются отдельно. Доступных живых устройств/тестовых ботов для этой работы нет; локальные фикстуры не выданы за реальную приемку.

## Проверка и источники

Узкая команда: `python -m unittest discover -s tests -p test_release_identity.py -v`. Тесты используют реальные раздельные temporary manifest paths, проверяют байты/mtime до и после success/refusal, отсутствие создаваемых файлов, canonical RC0/ordering/tag/filename boundaries и отказ неподдержанных форм. Выпуск не собирается.

Исходный helper: 16 tests passed, без skips, 5 ноября 2026. Узкие integration tests pipeline используют настоящие temporary git refs/manifests и ZIP/TAR archives: dirty checkout, missing/mismatched manifests, canonical RC artifacts/SBOM purls, recomputed RECORD при подмене source, numeric RC ordering, обязательные missing/blocked report failures и passed фикстуры. Embedded Python workflows компилируется локально; публикация не запускается. Полный verifier root выполняет отдельно после общей интеграции; эти проверки не объявляют выпуск готовым.

Локальный результат integration 5 ноября 2026: **74 tests passed**, без skips, Windows/Python 3.13.12, включая существующие helper/history tests. Shell blocks обоих workflows проверены `bash -n` без исполнения; Python heredoc blocks компилируются. `check_changelog.py` проходит для текущей numeric development version; исторические entries проверены по обеим доступным committed manifests. Лог: `output/production-run-2026-11-05/agent-034/release-pipeline-tests.txt`. Ни публикация, ни настоящие live/device проверки не выполнялись.

Фактически сверено 5 ноября 2026:

- [PyPA Version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/#pre-releases): canonical `rcN`, non-negative RC, normalization и более широкий разрешенный Python syntax.
- [PyPA Wheel distribution format](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode): distribution normalization и canonical version в wheel basename.
- [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html#spec-item-9): prerelease identifiers, отсутствие leading zero и precedence до final.
- [npm package.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#version) и [npm pack](https://docs.npmjs.com/cli/v11/commands/npm-pack/#description): semver version и tarball basename. Реализация scope-to-basename соответствует существующему контракту поставки проекта; это не обещание любых npm pack options.
- [npm/node-semver implementation](https://github.com/npm/node-semver/blob/main/classes/semver.js): `MAX_SAFE_INTEGER` bounds major/minor/patch. Общий модуль намеренно применяет ту же безопасную границу и к RC number.

Локальная политика: [versioning](../versioning.md), действующая процедура [releasing](../releasing.md). Источники объясняют формы; они не доказывают выполнение выпуска.
