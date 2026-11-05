/** Same-profile holdout comparison. This does not accept device or lifecycle gates. */
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {compare} from './metrics.mjs';
const read = async name => {
  const bytes = await readFile(name);
  return {report: JSON.parse(bytes), sha256: createHash('sha256').update(bytes).digest('hex')};
};
try {
  assert.equal(process.argv.length, 5, 'Supply baseline report, candidate report and absent output file');
  const baseline = await read(process.argv[2]), candidate = await read(process.argv[3]);
  assert.ok(baseline.report.measurements_completed && candidate.report.measurements_completed);
  assert.deepEqual(baseline.report.provenance, candidate.report.provenance, 'Artifact/source provenance differs');
  assert.deepEqual(baseline.report.asset_sha256, candidate.report.asset_sha256, 'Installed assets differ');
  const profile = report => {const value = {...report.profile};delete value.repetitions;return value;};
  assert.deepEqual(profile(baseline.report), profile(candidate.report), 'Measurement profiles differ');
  const measurements = {
    ready_observation_ms: candidate.report.load.map(row => row.ready_observation_ms),
    large_render_two_frames_ms: candidate.report.large_list.map(row => row.render_two_frames_ms),
    pointer_to_two_frames_ms: candidate.report.interactions.map(row => row.pointer_to_two_frames_ms),
  };
  const comparisons = Object.fromEntries(Object.entries(measurements).map(([key, values]) =>
    [key, compare(baseline.report.calibration[key], values)]));
  const result = {kind: 'local-performance-holdout', passed: Object.values(comparisons).every(value => value.passed),
    baseline_report_sha256: baseline.sha256, candidate_report_sha256: candidate.sha256,
    comparisons, full_fixture_passed: baseline.report.passed && candidate.report.passed,
    production_ready: false, limits: ['One same-host holdout is descriptive and does not establish production or target-device budgets.',
      'An incomplete lifecycle observation remains incomplete even when timing comparison passes.']};
  await writeFile(process.argv[4], JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({passed: result.passed, full_fixture_passed: result.full_fixture_passed, production_ready: false}));
  process.exitCode = result.passed ? 0 : 1;
} catch {
  console.error(JSON.stringify({passed: false, code: 'performance-comparison-refused'}));process.exitCode = 2;
}
