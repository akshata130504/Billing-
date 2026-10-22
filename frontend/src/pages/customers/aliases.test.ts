import { describe, expect, it } from 'vitest';
import * as oldIndex from './index';
import { CustomersListPage } from './CustomersListPage';
import { CustomerFormPage } from './CustomerFormPage';
import { CustomerDetailPage } from './CustomerDetailPage';
import * as customersModule from '../../modules/customers';

// pages/customers/ keeps only re-exports of src/modules/customers (modularization P1B). Routes and
// other features still import the old paths, so each must hand out the module's own components.
describe('pages/customers re-exports the Customers module', () => {
  it('gives the same objects through every old entry point', () => {
    expect(CustomersListPage).toBe(customersModule.CustomersListPage);
    expect(CustomerFormPage).toBe(customersModule.CustomerFormPage);
    expect(CustomerDetailPage).toBe(customersModule.CustomerDetailPage);
    expect(oldIndex.CustomersListPage).toBe(customersModule.CustomersListPage);
    expect(oldIndex.CustomerFormPage).toBe(customersModule.CustomerFormPage);
    expect(oldIndex.CustomerDetailPage).toBe(customersModule.CustomerDetailPage);
  });
});
