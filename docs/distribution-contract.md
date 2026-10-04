# Поставка локальных пакетов — 0.9.1

Пункт 009. Публичная Python поверхность — core `telegram_patterns`, optional `telegram_patterns.aiogram`/`testing` и console `telegram-patterns`. TypeScript — ESM root с declarations и отдельный `@awesome-telegram/patterns/styles.css`. Пакеты поставляются локально, не опубликованы в PyPI/npm. Интерфейсы и имена см. в [публичных контрактах](public-api.md), [структуре API](api-structure.md) и [адаптерах](extension-model.md).

## Что входит в артефакт

Wheel содержит Python modules, `py.typed`, bundled recipes JSON и все starter templates, включая `.env.example.txt` и mini-app templates. Это шаблон с искусственным token placeholder, а не конфигурация владельца. В core нет runtime зависимостей; aiogram подключается только extra. Console entry point совпадает с pyproject.scripts. Сейчас поставляется pure Python `py3-none-any`, Python >=3.11; это формат совместимости, а не подтверждение каждого Python/OS из диапазона.

Tarball содержит только package.json, README, compiled `dist/*.js` и соответствующие `dist/*.d.ts`, CSS. Каждый текущий source module имеет обе compiled части; private исходный TS, tests, .env, node_modules, старый dist module и дерево репозитория не входят. Export map содержит root `types`/`import` и styles.css; CSS остается declared side effect. CommonJS export сейчас отсутствует.

Dependencies, resource paths, новые export subpaths, compiled maps, license/data files меняются осознанно вместе с контрактом и verifier, а не проходят через общий permissive glob. Текущий allowlist лицензий пока не вводится: LICENSE/audit остаются пунктом 093, широкий релиз ими не подтвержден. Npm install зависимостей целевого проекта и отдельный build не означают публикацию пакета.

## Исполняемая проверка

После npm ci полная команда `python scripts/verify_pattern_packages.py` строит согласованные артефакты и вызывает [verify_distribution_contract.py](../scripts/verify_distribution_contract.py). Сам архивный helper читает ZIP/tar, ничего не извлекает, не импортирует архивный код и не заменяет файлы. Размер payload ограничен 8 MiB на файл, 32 MiB суммарно и 4096 entries; это лимит данного локального verifier, не лимит Telegram или стандарта упаковки.

Проверяются source/resource bytes, metadata identity/runtime/extra/CLI, полный RECORD со SHA256/size, public TS export map, declarations, CSS bytes и полный список tarball files. Missing/stale/extra files, mismatched versions, duplicate/traversal/backslash/absolute names, links и special members отклоняются. В wheel RECORD формат hashes/size сверялся по [спецификации PyPA](https://packaging.python.org/en/latest/specifications/binary-distribution-format/), checked 2026-10-04; наш verifier использует SHA256 и не является универсальным wheel installer. Npm files/export boundary сверялся с [официальным package.json](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/), checked 2026-10-04; наш allowlist строже общего npm pack behavior.

Проверка состава отдельно от runtime acceptance. Full verifier устанавливает wheel в два свежих venv: core без aiogram и SDK extra. Console/core/resources/starter, все owned root/adapter exports, Python typing consumers и runnable examples работают через installed package. Пример custom adapter копируется за пределы source tree. TypeScript tarball устанавливается в отдельный npm consumer; strict types, direct ESM imports, native compositions и CSS resolution проверяются без workspace package imports. Browser acceptance с installed tarball отдельно выполняется на generated starter. Основной example и gallery проверяются в workspace; их screenshots не выдаются за запуск вне source tree.

Temporary consumers запускаются вне repository cwd; PYTHONPATH/PYTHONHOME и BOT_TOKEN удалены из их окружения. Примеры и тестовые drivers могут читаться из репозитория как входные файлы, но их runtime imports должны разрешаться в установленный wheel/tarball; отдельный origin check подтверждает Python site-packages. Это доказывает независимость пакетов от исходного дерева, а не физическое удаление репозитория. Скомпилированные UI fixtures и copied starter позволяют проверить browser delivery отдельно.

## Отрицательные случаи и пределы

[test_distribution_contract.py](../tests/test_distribution_contract.py) создает настоящие архивы и source tree во временном каталоге: проверяет запуск CLI, сохранность owned файла, missing typing/resource/CSS/declaration, tampered source и RECORD, лишний secret fixture, устаревший dist, metadata и небезопасные archive entries. Проверка не печатает archived secret contents; контролируемая причина сообщает, какая граница нарушена.

Archive hash согласованности не подтверждает авторство или доверенный registry source. Supply chain/provenance относится к 095; этот helper не запускает sandbox malware analysis и не заменяет release review. Одна проверенная Windows/Python/Node/Chrome комбинация не доказывает все environments; [support matrix](support-matrix.md) сохраняет пределы. `--skip-browser` оставляет UI непроверенным явно. Telegram/live/provider/device evidence здесь не появляется.

Accepted artifact hashes фиксируются в docs/v1-checks и сохраняются с отдельной версией. Изменения этой проверки выпускаются как 0.9.1: существующие runtime API 0.9.0 сохранены, предыдущие артефакты не перезаписываются. Rebuild/release reproducibility и multi-version CI остаются собственными пунктами плана, а не закрываются проверкой имени архива.
