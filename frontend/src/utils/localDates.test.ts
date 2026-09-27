import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { addDays, paidAtForLocalDate, toIsoDate } from './format';

// Regression (browser QA): date fields defaulted with `new Date().toISOString().split('T')[0]`,
// which is the UTC date. In India (UTC+5:30) that is "yesterday" between 00:00 and 05:30, so
// a new quote was rejected with "Issue date cannot be in the past", and the weekly timesheet
// (local Monday midnight -> toISOString) requested the week starting on Sunday all day long.

const SRC = join(__dirname, '..');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

describe('local calendar dates', () => {
  it('toIsoDate uses the local calendar day, not the UTC one', () => {
    const justAfterMidnight = new Date(2026, 8, 27, 0, 30); // 27 Sep 2026 00:30 local
    expect(toIsoDate(justAfterMidnight)).toBe('2026-09-27');
    expect(addDays('2026-09-27', 30)).toBe('2026-10-27');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
  });

  // Regression: "Record Payment" dated today failed between 00:00 and 05:30 IST because the
  // client sent `${today}T00:00:00Z`, which the server (still on the previous UTC day) rejected.
  it('paidAtForLocalDate never stamps today in the future', () => {
    const now = new Date(2026, 8, 27, 1, 30); // 01:30 local on the 27th
    expect(paidAtForLocalDate(toIsoDate(now), now)).toBe(now.toISOString());
    expect(paidAtForLocalDate('', now)).toBe(now.toISOString());
    expect(Date.parse(paidAtForLocalDate(toIsoDate(now), now))).toBeLessThanOrEqual(now.getTime());
    // Past days keep the noon-UTC anchor.
    expect(paidAtForLocalDate('2026-09-07', now)).toBe('2026-09-07T12:00:00.000Z');
  });

  it('no component derives a YYYY-MM-DD value from toISOString()', () => {
    const offenders = sourceFiles(SRC)
      .filter((f) => /toISOString\(\)\s*\.\s*(split\(\s*'T'\s*\)\[0\]|slice\(0,\s*10\)|substring\(0,\s*10\))/.test(readFileSync(f, 'utf8')))
      .map((f) => relative(SRC, f));
    expect(offenders).toEqual([]);
  });
});
