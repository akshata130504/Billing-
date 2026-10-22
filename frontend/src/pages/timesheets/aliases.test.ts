import { describe, expect, it } from 'vitest';
import { TimesheetsPage } from './TimesheetsPage';
import * as timesheetsModule from '../../modules/timesheets';

// pages/timesheets/ keeps only a re-export of src/modules/timesheets (modularization P1B); the UI
// preview still imports the old path, so it must hand out the module's own component.
describe('pages/timesheets re-exports the Timesheets module', () => {
  it('gives the same component through the old entry point', () => {
    expect(TimesheetsPage).toBe(timesheetsModule.TimesheetsPage);
  });
});
