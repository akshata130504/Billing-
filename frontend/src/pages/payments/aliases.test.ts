import { describe, expect, it } from 'vitest';
import * as old0 from './PaymentsContext';
import * as new0 from '../../modules/payments/PaymentsContext';
import * as old1 from './PaymentsPage';
import * as new1 from '../../modules/payments/PaymentsPage';

// pages/payments/ keeps only re-exports of src/modules/payments (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['PaymentsContext', old0, new0],
    ['PaymentsPage', old1, new1],
];

describe('pages/payments re-exports the payments module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
