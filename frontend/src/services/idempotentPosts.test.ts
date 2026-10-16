import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('./apiClient', async (orig) => ({ ...(await orig<typeof import('./apiClient')>()), apiClient: api }));

import { invoiceService } from './invoiceService';
import { paymentService } from './paymentService';
import { subscriptionService } from './subscriptionService';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const keyOf = (call: unknown[]) => (call[2] as { headers: Record<string, string> }).headers['Idempotency-Key'];

// Money-moving and record-creating POSTs carry an Idempotency-Key so a retry (double submit,
// the 401-refresh replay, a resubmit after a lost response) cannot create a second record.
describe('idempotent POSTs', () => {
  beforeEach(() => {
    api.post.mockReset();
    api.post.mockResolvedValue({ data: { id: 'x' } });
  });

  it.each([
    ['record payment on an invoice', () => invoiceService.recordPayment('inv-1', { amount: 10, payment_date: '2026-10-01', payment_method: 'cash', reference_number: '', notes: '' })],
    ['create a payment', () => paymentService.create({ customer_id: 'c', amount: '10', method: 'cash' } as never)],
    ['create a subscription', () => subscriptionService.create({ customer_id: 'c', plan_id: 'p' } as never)],
  ])('%s sends a fresh key by default', async (_label, send) => {
    await send();
    await send();
    const [first, second] = api.post.mock.calls.map(keyOf);
    expect(first).toMatch(UUID_V4);
    expect(second).toMatch(UUID_V4);
    expect(first).not.toBe(second);
  });

  it('reuses the key the caller passes, for every retry of the same submission', async () => {
    await invoiceService.recordPayment('inv-1', { amount: 10, payment_date: '2026-10-01', payment_method: 'cash', reference_number: '', notes: '' }, 'form-key');
    await paymentService.create({ customer_id: 'c', amount: '10', method: 'cash' } as never, 'form-key');
    await subscriptionService.create({ customer_id: 'c', plan_id: 'p' } as never, 'form-key');
    expect(api.post.mock.calls.map(keyOf)).toEqual(['form-key', 'form-key', 'form-key']);
  });
});
