import { describe, expect, it } from 'vitest';
import * as old0 from './SubscriptionsListPage';
import * as new0 from '../../modules/subscriptions/SubscriptionsListPage';
import * as old1 from './TrialsPage';
import * as new1 from '../../modules/subscriptions/TrialsPage';

// pages/subscriptions/ keeps only re-exports of src/modules/subscriptions (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['SubscriptionsListPage', old0, new0],
    ['TrialsPage', old1, new1],
];

describe('pages/subscriptions re-exports the subscriptions module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
