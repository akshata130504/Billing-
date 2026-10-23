import { describe, expect, it } from 'vitest';
import { catalogService } from './catalogService';
import { catalogService as fromBarrel } from './index';
import * as productsModule from '../modules/products';

// services/catalogService.ts is a re-export of src/modules/products (modularization P1B). Six
// features and a vi.mock target still use the old path, so it must be the module's own object.
describe('services/catalogService re-exports the Products module', () => {
  it('gives the same object through every old entry point', () => {
    expect(catalogService).toBe(productsModule.catalogService);
    expect(fromBarrel).toBe(productsModule.catalogService);
  });
});
