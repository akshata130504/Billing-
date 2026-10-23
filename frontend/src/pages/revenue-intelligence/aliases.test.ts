import { describe, expect, it } from 'vitest';
import * as old0 from './RevenueIntelligencePage';
import * as new0 from '../../modules/reports/revenue-intelligence/RevenueIntelligencePage';

// pages/revenue-intelligence/ keeps only re-exports of src/modules/reports (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['RevenueIntelligencePage', old0, new0],
];

describe('pages/revenue-intelligence re-exports the reports module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
