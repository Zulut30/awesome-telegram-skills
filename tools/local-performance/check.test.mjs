import assert from 'node:assert/strict';
import {execFileSync, spawnSync} from 'node:child_process';
import {copyFileSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {compare, summary} from './metrics.mjs';

const script = fileURLToPath(new URL('./run.mjs', import.meta.url));
test('calibration retains raw variation; a measured regression fails', () => {
  const baseline = summary([10, 11, 12, 13, 14]);
  assert.equal(baseline.median, 12);
  assert.equal(baseline.median_absolute_deviation, 1);
  assert.equal(baseline.provisional_limit, 17);
  assert.equal(compare(baseline, [12, 14, 16]).passed, true);
  assert.equal(compare(baseline, [12, 14, 18]).passed, false);
  assert.deepEqual(baseline.samples, [10, 11, 12, 13, 14]);
  const even = summary([1, 3, 7, 9]);
  assert.equal(even.median, 5);
  assert.equal(even.median_absolute_deviation, 3);
});
test('incomplete or invalid measurement samples cannot become zero latency', () => {
  for (const samples of [[], [1], [1, 2, NaN], [1, 2, -1], [1, 2, Infinity], [0, 1e308, 1.7e308]]) {
    assert.throws(() => summary(samples));
  }
});
test('existing output refuses without replacing caller files or reading supplied assets', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'local-performance-caller-'));
  try {
    const output = path.join(root, 'owned');mkdirSync(output);
    const marker = path.join(output, 'owner.txt');writeFileSync(marker, 'preserve exact caller bytes');
    const config = path.join(root, 'configuration.json');
    writeFileSync(config, JSON.stringify({distributionReport: 'absent', acceptance: 'absent', tarball: 'absent', output}));
    // A copied preflight has no checkout node_modules; only actual Chrome work needs Playwright.
    const portable = path.join(root, 'run.mjs');copyFileSync(script, portable);
    copyFileSync(fileURLToPath(new URL('./metrics.mjs', import.meta.url)), path.join(root, 'metrics.mjs'));
    const done = spawnSync(process.execPath, [portable, config], {cwd: root, encoding: 'utf8', timeout: 10000});
    assert.equal(done.status, 2);assert.match(done.stderr, /refused-or-failed/);
    assert.equal(readFileSync(marker, 'utf8'), 'preserve exact caller bytes');
  } finally {rmSync(root, {recursive: true, force: true});}
});
test('linked output refuses without following a caller-owned destination', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'local-performance-link-'));
  try {
    const destination = path.join(root, 'owned');mkdirSync(destination);
    writeFileSync(path.join(destination, 'owner.txt'), 'keep');
    const link = path.join(root, 'link');
    if (process.platform === 'win32') execFileSync('cmd', ['/c', 'mklink', '/J', link, destination], {stdio: 'ignore'});
    else execFileSync(process.execPath, ['-e', 'require("fs").symlinkSync(process.argv[1],process.argv[2],"dir")', destination, link]);
    const config = path.join(root, 'configuration.json');
    writeFileSync(config, JSON.stringify({distributionReport: 'absent', acceptance: 'absent', tarball: 'absent', output: path.join(link, 'new')}));
    const done = spawnSync(process.execPath, [script, config], {cwd: root, encoding: 'utf8', timeout: 10000});
    assert.equal(done.status, 2);assert.equal(readFileSync(path.join(destination, 'owner.txt'), 'utf8'), 'keep');
  } finally {rmSync(root, {recursive: true, force: true});}
});
test('real comparison writes holdout result, detects regression and refuses wrong profile/overwrite', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'local-performance-comparison-'));
  const comparison = fileURLToPath(new URL('./compare.mjs', import.meta.url));
  const invoke = (baseline, candidate, output) => spawnSync(process.execPath,
    [comparison, baseline, candidate, output], {cwd: root, encoding: 'utf8', timeout: 10000});
  try {
    const baseline = {measurements_completed: true, passed: false,
      profile: {viewport: {width: 390, height: 844}, repetitions: 5},
      provenance: {version: 'synthetic-test-only'}, asset_sha256: [],
      load: [10, 11, 12, 13, 14].map(value => ({ready_observation_ms: value})),
      large_list: [10, 11, 12, 13, 14].map(value => ({render_two_frames_ms: value})),
      interactions: [10, 11, 12, 13, 14].map(value => ({pointer_to_two_frames_ms: value})),
      calibration: Object.fromEntries(['ready_observation_ms', 'large_render_two_frames_ms',
        'pointer_to_two_frames_ms'].map(key => [key, summary([10, 11, 12, 13, 14])]))};
    const baseFile = path.join(root, 'baseline.json'), candidateFile = path.join(root, 'candidate.json');
    writeFileSync(baseFile, JSON.stringify(baseline));writeFileSync(candidateFile, JSON.stringify(baseline));
    const positive = path.join(root, 'positive.json');assert.equal(invoke(baseFile, candidateFile, positive).status, 0);
    const saved = readFileSync(positive);assert.equal(JSON.parse(saved).full_fixture_passed, false);
    assert.equal(JSON.parse(saved).production_ready, false);
    assert.equal(invoke(baseFile, candidateFile, positive).status, 2);assert.deepEqual(readFileSync(positive), saved);
    const mutated = structuredClone(baseline);mutated.interactions[0].pointer_to_two_frames_ms = 18;
    writeFileSync(candidateFile, JSON.stringify(mutated));
    const negative = path.join(root, 'negative.json');assert.equal(invoke(baseFile, candidateFile, negative).status, 1);
    assert.equal(JSON.parse(readFileSync(negative)).comparisons.pointer_to_two_frames_ms.passed, false);
    mutated.profile.viewport.width = 320;writeFileSync(candidateFile, JSON.stringify(mutated));
    assert.equal(invoke(baseFile, candidateFile, path.join(root, 'wrong-profile.json')).status, 2);
  } finally {rmSync(root, {recursive: true, force: true});}
});
test('targeted lifecycle preflight also preserves existing output outside checkout', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'local-lifecycle-preflight-'));
  try {
    const here = path.dirname(script);
    for (const name of ['run.mjs', 'metrics.mjs', 'lifecycle.mjs', 'owned-browser.mjs']) {
      copyFileSync(path.join(here, name), path.join(root, name));
    }
    const output = path.join(root, 'owned');mkdirSync(output);writeFileSync(path.join(output, 'owner.txt'), 'unchanged');
    const config = path.join(root, 'configuration.json');
    writeFileSync(config, JSON.stringify({distributionReport: 'absent', acceptance: 'absent', tarball: 'absent', output}));
    const done = spawnSync(process.execPath, [path.join(root, 'lifecycle.mjs'), config], {cwd: root, encoding: 'utf8', timeout: 10000});
    assert.equal(done.status, 2);assert.match(done.stderr, /targeted-lifecycle-refused-or-failed/);
    assert.equal(readFileSync(path.join(output, 'owner.txt'), 'utf8'), 'unchanged');
  } finally {rmSync(root, {recursive: true, force: true});}
});
