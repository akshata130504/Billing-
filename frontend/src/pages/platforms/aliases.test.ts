import { describe, expect, it } from 'vitest';
import * as old0 from './DesktopPlatformPage';
import * as new0 from '../../modules/platforms/DesktopPlatformPage';
import * as old1 from './MobilePlatformPage';
import * as new1 from '../../modules/platforms/MobilePlatformPage';

// pages/platforms/ keeps only re-exports of src/modules/platforms (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['DesktopPlatformPage', old0, new0],
    ['MobilePlatformPage', old1, new1],
];

describe('pages/platforms re-exports the platforms module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
