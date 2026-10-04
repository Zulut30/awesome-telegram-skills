/** Fixture assertions; this helper does not belong to the library API. */
export function check(value: unknown, message = 'Reference fixture failed'): asserts value {
  if (!value) throw new Error(message);
}
