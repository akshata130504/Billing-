import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { validateDateNotFuture, validateDateNotPast } from './validation';

// A date input's "YYYY-MM-DD" is a local calendar day. Parsing it with new Date() gives midnight UTC,
// which is the previous day west of UTC: today's date was rejected as past, tomorrow's accepted.
describe.each(['America/Los_Angeles', 'Asia/Kolkata', 'UTC'])('date-only checks in %s', (tz) => {
  const originalTz = process.env.TZ;

  beforeEach(() => {
    process.env.TZ = tz;
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 16, 9, 0, 0)); // 16 Oct 2026, 09:00 local
  });

  afterEach(() => {
    vi.useRealTimers();
    process.env.TZ = originalTz;
  });

  it('accepts today as neither past nor future', () => {
    expect(validateDateNotPast('2026-10-16', 'Issue date')).toBeNull();
    expect(validateDateNotFuture('2026-10-16', 'Payment date')).toBeNull();
  });

  it('rejects yesterday as past and tomorrow as future', () => {
    expect(validateDateNotPast('2026-10-15', 'Issue date')).toBe('Issue date cannot be in the past.');
    expect(validateDateNotFuture('2026-10-17', 'Payment date')).toBe('Payment date cannot be later than today.');
  });

  it('still reports malformed dates', () => {
    expect(validateDateNotPast('2026-13-40', 'Issue date')).toBe('Issue date is invalid.');
  });
});
