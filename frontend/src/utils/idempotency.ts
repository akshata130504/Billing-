/** RFC 4122 v4 id; falls back to a Math.random-based generator on very old browsers. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Request config carrying an `Idempotency-Key` header. The backend runs a keyed POST at most once
 * per organization, so a retry (double submit, the 401-refresh replay in apiClient, a resubmit after
 * a network error) returns the original record instead of creating a second one.
 */
export function idempotencyHeaders(key: string = newIdempotencyKey()) {
  return { headers: { 'Idempotency-Key': key } };
}
