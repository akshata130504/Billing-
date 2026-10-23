import { describe, expect, it } from 'vitest';
import * as old0 from './IntegrationsTab';
import * as new0 from '../../modules/integrations/IntegrationsTab';

// pages/settings/ keeps only re-exports of src/modules/integrations (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['IntegrationsTab', old0, new0],
];

describe('pages/settings re-exports the integrations module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
