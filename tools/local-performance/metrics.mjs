/** Descriptive local calibration, never a production or target-device SLA. */
import assert from 'node:assert/strict';
export function summary(samples) {
  assert.ok(Array.isArray(samples) && samples.length >= 3 && samples.every(Number.isFinite));
  assert.ok(samples.every(value => value >= 0));
  const sorted = [...samples].sort((a, b) => a - b);
  const middle = values => {
    const index = Math.floor(values.length / 2);
    return values.length % 2 ? values[index] : values[index - 1] + (values[index] - values[index - 1]) / 2;
  };
  const median = middle(sorted);
  const deviations = samples.map(value => Math.abs(value - median)).sort((a, b) => a - b);
  const mad = middle(deviations);
  const provisionalLimit = sorted.at(-1) + 3 * mad;
  assert.ok(Number.isFinite(provisionalLimit), 'Calibration limit must remain finite');
  return {samples: [...samples], minimum: sorted[0], median, maximum: sorted.at(-1),
    median_absolute_deviation: mad, provisional_limit: provisionalLimit};
}
export function compare(baseline, samples) {
  const measured = summary(samples);
  assert.ok(Number.isFinite(baseline.provisional_limit) && baseline.provisional_limit >= 0);
  return {passed: measured.maximum <= baseline.provisional_limit, measured,
    limit: baseline.provisional_limit,
    scope: 'Same-profile laboratory regression sentinel; no production SLA or field percentile.'};
}
