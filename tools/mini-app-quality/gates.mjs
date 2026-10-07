/** Threshold checks for the Mini App demo. Pure: the CI job fails when evaluate() returns any failure. */

export function median(values) {
  if (!values.length) return Number.NaN;
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** Human-readable failures of measured results against budgets.json; an empty list means every gate passed. */
export function evaluate(measured, budgets) {
  const failures = [];
  for (const [category, minimum] of Object.entries(budgets.lighthouse.min_scores)) {
    const score = measured.lighthouse[category];
    // A missing score (null when Lighthouse could not compute it) is a failure, not a pass.
    if (typeof score !== 'number' || !(score >= minimum)) failures.push(`Lighthouse ${category}: ${score} < ${minimum}`);
  }
  const limits = [['script_bytes', 'max_script_bytes'], ['stylesheet_bytes', 'max_stylesheet_bytes'], ['requests', 'max_requests']];
  for (const [field, limit] of limits) {
    const value = measured.bundle[field], maximum = budgets.bundle[limit];
    if (!Number.isInteger(value) || !Number.isInteger(maximum) || value > maximum) failures.push(`Bundle ${field}: ${value} > ${maximum}`);
  }
  const violations = measured.axe.flatMap(state => state.violations.map(item => `${state.name}: ${item.id} (${item.impact}, ${item.nodes})`));
  if (violations.length > budgets.axe.max_violations) failures.push(`axe: ${violations.length} violations — ${violations.join('; ')}`);
  return failures;
}
