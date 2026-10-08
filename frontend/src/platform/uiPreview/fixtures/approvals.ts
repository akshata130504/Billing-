/** Visual-editor preview sample data for the Approval Center (/control-center/approvals). Fictional. */
import type { ApprovalOut, Paginated, UserRef } from '../../../types/api';

const requester: UserRef = { id: 'user-2', full_name: 'Ravi Menon', email: 'ravi@example.com' };
const reviewer: UserRef = { id: 'user-1', full_name: 'Asha Sharma', email: 'asha@example.com' };

const sampleApprovals: ApprovalOut[] = [
  {
    id: 'apr-1', type: 'quote_discount', status: 'pending', entity_type: 'quote',
    entity_id: '00000000-0000-4000-d000-000000000034', entity_label: 'QT-0034',
    title: '25% discount on Growth plan annual quote', justification: 'Multi-year commitment from a strategic account.',
    payload: { discount_pct: '25', threshold_pct: '20', quote_total: '184000.00' },
    requested_by: requester, reviewed_by: null, reviewed_at: null, decision_note: null, created_at: '2026-10-03T10:15:00Z',
  },
  {
    id: 'apr-2', type: 'refund', status: 'pending', entity_type: 'payment',
    entity_id: '00000000-0000-4000-c000-000000000207', entity_label: 'PAY-0207',
    title: 'Refund duplicate card payment', justification: 'Customer was charged twice for INV-1039.',
    payload: { amount: '12980.00', reason: 'duplicate' },
    requested_by: requester, reviewed_by: null, reviewed_at: null, decision_note: null, created_at: '2026-10-02T14:40:00Z',
  },
  {
    id: 'apr-3', type: 'invoice_void', status: 'approved', entity_type: 'invoice',
    entity_id: '00000000-0000-4000-b000-000000001036', entity_label: 'INV-1036',
    title: 'Void invoice raised against the wrong customer', justification: null,
    payload: {},
    requested_by: requester, reviewed_by: reviewer, reviewed_at: '2026-09-29T09:05:00Z', decision_note: 'Re-issued as INV-1037.',
    created_at: '2026-09-28T16:20:00Z',
  },
  {
    id: 'apr-4', type: 'invoice_discount', status: 'rejected', entity_type: 'invoice',
    entity_id: '00000000-0000-4000-b000-000000001033', entity_label: 'INV-1033',
    title: '30% goodwill discount', justification: 'Delayed onboarding.',
    payload: { discount_pct: '30' },
    requested_by: requester, reviewed_by: reviewer, reviewed_at: '2026-09-25T11:30:00Z', decision_note: 'Offer a service credit instead.',
    created_at: '2026-09-24T08:45:00Z',
  },
];

function listApprovals(query: URLSearchParams): Paginated<ApprovalOut> {
  const status = query.get('status');
  const items = sampleApprovals.filter((a) => !status || a.status === status);
  return { items, total: items.length, page: 1, page_size: Math.max(items.length, 20), total_pages: 1 };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/approvals': listApprovals,
};
