"""План перед запуском; установленный core wheel, без SDK и Telegram."""
import json
from telegram_patterns import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline

plan: RecipeRunPlan = plan_recipe('demo-recovery')
assert plan.offline_ready and plan.kind == 'sqlite'
assert not plan.offline_environment and not plan.offline_permissions
assert plan.live_data and plan.live_permissions and plan.sources
result: RecipeRunResult = run_recipe_offline(plan.recipe_id)
assert result.passed and not result.telegram_requests
assert result.checks == ('sqlite-one-effect', 'same-key-replay')
reference = plan_recipe('native.requestContact')
assert not reference.offline_ready and reference.live_permissions
print(json.dumps({'passed': True, 'case': 'core_execution', 'network': False}))
