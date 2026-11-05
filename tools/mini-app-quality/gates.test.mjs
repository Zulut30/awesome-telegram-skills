import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {evaluate, median, summarizeAxeAudit} from './gates.mjs';

const budgets = JSON.parse(await readFile(new URL('./budgets.json', import.meta.url), 'utf8'));
const passing = () => ({
  lighthouse: {performance: 0.97, accessibility: 1},
  bundle: {script_bytes: budgets.bundle.max_script_bytes, stylesheet_bytes: 100, requests: 3},
  axe: [{name: 'phone-light', violations: []}],
});

test('median of Lighthouse runs', () => {
  assert.equal(median([0.91, 0.5, 0.99]), 0.91);
  assert.equal(median([0.8, 1]), 0.9);
  assert.ok(Number.isNaN(median([])));
});

test('incomplete axe findings survive a green automatic budget and require manual review', () => {
  const raw = {passes: [{id: 'label'}], violations: [], incomplete: [{id: 'color-contrast',
    impact: 'serious', help: 'Review contrast', nodes: [{target: ['#gradient'], html: 'not retained'}]}]};
  const state = summarizeAxeAudit('manual-review', raw);
  const measured = passing(); measured.axe = [state];
  assert.deepEqual(evaluate(measured, budgets), []);
  assert.equal(state.manual_review_required, true);
  assert.equal(state.wcag_conformance, 'not-assessed');
  assert.equal(state.incomplete[0].id, 'color-contrast');
  assert.deepEqual(state.incomplete[0].targets, [['#gradient']]);
  assert.equal(JSON.stringify(state).includes('not retained'), false);
  assert.equal(raw.incomplete.length, 1);
  assert.equal(summarizeAxeAudit('no-incomplete', {...raw, incomplete: []}).manual_review_required, false);
});

test('missing axe incomplete data cannot masquerade as an empty manual review queue', () => {
  assert.throws(() => summarizeAxeAudit('missing', {passes: [], violations: []}), /Complete axe/);
});

test('budgets pass at the limit and fail just past it', () => {
  assert.deepEqual(evaluate(passing(), budgets), []);
  const cases = [
    [m => { m.lighthouse.performance = 0.89; }, /performance: 0.89 < 0.9/],
    [m => { m.lighthouse.accessibility = 0.94; }, /accessibility: 0.94 < 0.95/],
    [m => { m.lighthouse.performance = null; }, /performance: null/],
    [m => { m.bundle.script_bytes += 1; }, /script_bytes/],
    [m => { m.bundle.stylesheet_bytes = budgets.bundle.max_stylesheet_bytes + 1; }, /stylesheet_bytes/],
    [m => { m.bundle.requests = budgets.bundle.max_requests + 1; }, /requests/],
    [m => { m.axe[0].violations.push({id: 'color-contrast', impact: 'serious', nodes: 2}); }, /axe: 1 violations — phone-light: color-contrast \(serious, 2\)/],
  ];
  for (const [change, message] of cases) {
    const measured = passing(); change(measured);
    const failures = evaluate(measured, budgets);
    assert.equal(failures.length, 1, String(message)); assert.match(failures[0], message);
  }
});
