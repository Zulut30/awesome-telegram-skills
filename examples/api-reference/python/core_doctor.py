"""Doctor запускается SDK-free: диагностика readiness, не автоматический install."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from telegram_patterns.cli import doctor

with TemporaryDirectory() as folder:
    project = Path(folder)
    (project / 'pyproject.toml').write_text('[project]\nname="fixture"\n', encoding='utf-8')
    (project / '.env').write_text('BOT_TOKEN=PRIVATE_FIXTURE', encoding='utf-8')
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    report = doctor(project)
    checks = {check['name']: check for check in report['checks']}
    assert checks['aiogram']['reason'] == 'sdk-missing'
    assert not report['passed'] and not report['network'] and not report['suggestions_executed']
    assert checks['aiogram']['remediation']['commands'] and 'PRIVATE_FIXTURE' not in json.dumps(report)
    assert before == {p.name: p.read_bytes() for p in project.iterdir()}
print(json.dumps({'passed': True, 'case': 'core_doctor', 'network': False}))
