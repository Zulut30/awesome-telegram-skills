"""Предоставленный wheel передается явно; генерируем только новый temp target."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from telegram_patterns import StarterPlan, StarterComponent, StarterConflict, starter_components, create_starter

wheel = Path(sys.argv[1]).resolve(strict=True)
component: StarterComponent = next(c for c in starter_components('bot') if c.id == 'text-form')
assert component.min_library_version == '0.8.0'
with TemporaryDirectory() as folder:
    target = Path(folder) / 'new bot'
    plan: StarterPlan = create_starter(target, library=wheel, components=['text-form'], dry_run=True)
    assert not target.exists() and not plan.created and 'starter_form.py' in plan.files
    created = create_starter(target, library=wheel, components=['text-form'])
    assert created.created and created.files == plan.files and component.id in created.components
    before = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    try: create_starter(target, library=wheel)
    except FileExistsError: pass
    else: raise AssertionError('Existing project overwritten')
    assert before == {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    try: create_starter(Path(folder) / 'invalid', library=wheel, components=['api-client'])
    except StarterConflict as error: assert error.reason == 'component-template'
    else: raise AssertionError('Incompatible selection accepted')
print(json.dumps({'passed': True, 'case': 'core_starter', 'network': False}))
