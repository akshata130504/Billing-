import { describe, expect, it } from 'vitest';
import * as old0 from './CPQPage';
import * as new0 from '../../modules/quotes/cpq/CPQPage';

// pages/cpq/ keeps only re-exports of src/modules/quotes (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['CPQPage', old0, new0],
];

describe('pages/cpq re-exports the quotes module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
