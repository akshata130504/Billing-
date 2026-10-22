import { describe, expect, it } from 'vitest';
import * as old0 from './ExpensesContext';
import * as new0 from '../../modules/expenses/ExpensesContext';
import * as old1 from './ExpensesPage';
import * as new1 from '../../modules/expenses/ExpensesPage';
import * as old2 from './types';
import * as new2 from '../../modules/expenses/types';
import * as old3 from './useCustomerProjects';
import * as new3 from '../../modules/expenses/useCustomerProjects';

// pages/expenses/ keeps only re-exports of src/modules/expenses (modularization P1B) for the old
// paths other features still import. Each must hand out the module's own objects, under the same names.
const ALIASES: [string, Record<string, unknown>, Record<string, unknown>][] = [
    ['ExpensesContext', old0, new0],
    ['ExpensesPage', old1, new1],
    ['types', old2, new2],
    ['useCustomerProjects', old3, new3],
];

describe('pages/expenses re-exports the expenses module', () => {
  it.each(ALIASES)('%s gives the same objects as the module file', (_name, oldPath, newPath) => {
    expect(Object.keys(oldPath).sort()).toEqual(Object.keys(newPath).sort());
    for (const key of Object.keys(newPath)) expect(oldPath[key]).toBe(newPath[key]);
  });
});
