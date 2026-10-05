"""SDK-free server draft: configured values, revisions and bound confirmation."""
from dataclasses import replace
import json
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionResult, SelectionSpec, SelectionState

context = SelectionContext(100, 42, 42, 100)
rules = SelectionSpec([SelectionOption('a', 'Alpha', ['basic']), SelectionOption('b', 'Beta')],
                      toggles={'notify':'Уведомлять'}, filters={'all':'Все','basic':'Основные'},
                      quantity_min=1, quantity_max=3, min_selected=1, max_selected=2)
menu = SelectionMenu(rules, context)
initial: SelectionState = menu.state
denied: SelectionResult = menu.apply(initial.callback('s:a'), replace(context, owner_id=43))
assert denied.status == 'denied' and denied.state is None and menu.state is initial
assert menu.apply(initial.callback('s:a'), context).status == 'accepted'
assert menu.apply(initial.callback('s:a'), context).status == 'stale'
for action in ('s:b','t:notify','q:inc','f:basic','ask'):
    assert menu.apply(menu.state.callback(action), context).status in {'accepted','confirming'}
pending = menu.state
assert pending.confirmation_id is not None
old_confirmation = pending.callback('y:' + pending.confirmation_id)
menu.replace_spec(replace(rules, resource_version='2'))
assert menu.apply(old_confirmation, context).status == 'stale'
assert menu.state.selected == ('a','b')
assert menu.apply(menu.state.callback('ask'), context).status == 'confirming'
pending = menu.state
assert pending.confirmation_id is not None
data = pending.callback('y:' + pending.confirmation_id)
result = menu.apply(data, context)
assert result.status == 'confirmed' and result.state is not None and result.state.operation_id is not None
assert result.state.spec.resource_version == '2'
assert menu.apply(data, context).status == 'stale'
print(json.dumps({'passed':True,'case':'core_selection','network':False,'business_effects':0}))
