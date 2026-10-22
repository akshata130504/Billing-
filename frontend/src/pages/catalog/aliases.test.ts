import { describe, expect, it } from 'vitest';
import { CatalogPage } from './CatalogPage';
import * as productsModule from '../../modules/products';

// pages/catalog/ keeps only a re-export of src/modules/products (modularization P1B); the UI preview
// still imports the old path, so it must hand out the module's own component.
describe('pages/catalog re-exports the Products module', () => {
  it('gives the same component through the old entry point', () => {
    expect(CatalogPage).toBe(productsModule.CatalogPage);
  });
});
