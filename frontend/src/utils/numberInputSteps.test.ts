import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

// Regression (browser QA): the timesheet Duration input had step="0.25" min="0.1", so the
// browser only accepted 0.1, 0.35, 0.6, ... and blocked whole hours and the 2.5 h that the
// start/end times auto-filled ("nearest valid values are 2.35 and 2.6"). Entries could not be
// saved. Guard: when an input declares both min and step, whole numbers >= min must be valid.

const SRC = join(__dirname, '..');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [full] : [];
  });
}

/** True when `value` is an integer multiple of `step` (within float noise). */
function isMultiple(value: number, step: number): boolean {
  const q = value / step;
  return Math.abs(q - Math.round(q)) < 1e-9;
}

describe('number inputs with min + step', () => {
  it('accept every whole number at or above min', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(file, 'utf8');
      // Each JSX opening tag that mentions both attributes (attributes may span lines).
      for (const tag of text.match(/<(input|Input)\b[^>]*>/gs) ?? []) {
        const step = /\bstep="([\d.]+)"/.exec(tag)?.[1];
        const min = /\bmin="([\d.]+)"/.exec(tag)?.[1];
        if (!step || !min) continue;
        const s = Number(step);
        const m = Number(min);
        if (!isMultiple(m, s) || !isMultiple(1, s)) {
          offenders.push(`${relative(SRC, file)}: min="${min}" step="${step}"`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
