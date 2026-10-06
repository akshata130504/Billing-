/**
 * Visual-editor preview sample data for Control Center > Audit Log (/control-center/audit-log).
 * Entirely fictional (example.in addresses, documentation-range IPs, made-up names).
 */
import type { AuditLogOut, Paginated } from '../../../types/api';

const actors = {
  asha: { id: 'preview-user-1', full_name: 'Asha Rao', email: 'asha.rao@example.in' },
  vikram: { id: 'preview-user-2', full_name: 'Vikram Menon', email: 'vikram.menon@example.in' },
  neha: { id: 'preview-user-3', full_name: 'Neha Kulkarni', email: 'neha.k@example.in' },
};

const AUDIT_LOGS: AuditLogOut[] = [
  {
    id: 'aud-preview-0008', created_at: '2026-10-05T16:42:10Z', actor: actors.asha, actor_label: 'Asha Rao',
    action: 'INVOICE_VOIDED', entity_type: 'invoice', entity_id: 'inv-preview-1040', entity_label: 'INV-1040',
    status: 'success', before_state: { status: 'sent', total: '9440.00' }, after_state: { status: 'void' }, ip_address: '203.0.113.24',
  },
  {
    id: 'aud-preview-0007', created_at: '2026-10-05T11:08:55Z', actor: actors.vikram, actor_label: 'Vikram Menon',
    action: 'QUOTE_DISCOUNT_APPROVED', entity_type: 'approval', entity_id: 'apr-preview-12', entity_label: 'QT-0217 discount 18%',
    status: 'success', before_state: { status: 'pending' }, after_state: { status: 'approved' }, ip_address: '198.51.100.7',
  },
  {
    id: 'aud-preview-0006', created_at: '2026-10-04T09:30:02Z', actor: actors.neha, actor_label: 'Neha Kulkarni',
    action: 'PAYMENT_RECORDED', entity_type: 'payment', entity_id: 'pay-preview-311', entity_label: 'PAY-00311',
    status: 'success', before_state: null, after_state: { amount: '24780.00', method: 'bank_transfer' }, ip_address: '203.0.113.51',
  },
  {
    id: 'aud-preview-0005', created_at: '2026-10-03T18:15:40Z', actor: actors.asha, actor_label: 'Asha Rao',
    action: 'PLAN_PRICE_CHANGED', entity_type: 'plan', entity_id: 'plan-preview-4', entity_label: 'Growth (Monthly)',
    status: 'warning', before_state: { unit_amount: '4999.00' }, after_state: { unit_amount: '5499.00' }, ip_address: '203.0.113.24',
  },
  {
    id: 'aud-preview-0004', created_at: '2026-10-02T07:55:19Z', actor: null, actor_label: 'Unknown sign-in',
    action: 'LOGIN_DENIED', entity_type: 'user', entity_id: null, entity_label: 'ops@example.in',
    status: 'denied', before_state: null, after_state: null, ip_address: '192.0.2.88',
  },
  {
    id: 'aud-preview-0003', created_at: '2026-10-01T13:20:00Z', actor: actors.vikram, actor_label: 'Vikram Menon',
    action: 'CUSTOMER_UPDATED', entity_type: 'customer', entity_id: 'cust-preview-3', entity_label: 'Lotus Textiles',
    status: 'success', before_state: { payment_terms_days: 15 }, after_state: { payment_terms_days: 30 }, ip_address: '198.51.100.7',
  },
  {
    id: 'aud-preview-0002', created_at: '2026-09-30T10:05:33Z', actor: actors.neha, actor_label: 'Neha Kulkarni',
    action: 'IMPORT_COMPLETED', entity_type: 'import', entity_id: 'imp-preview-2', entity_label: 'products_sample.csv',
    status: 'success', before_state: null, after_state: { imported_rows: 42, failed_rows: 0 }, ip_address: '203.0.113.51',
  },
  {
    id: 'aud-preview-0001', created_at: '2026-09-29T15:47:12Z', actor: actors.asha, actor_label: 'Asha Rao',
    action: 'MEMBER_ROLE_CHANGED', entity_type: 'membership', entity_id: 'mem-preview-3', entity_label: 'Neha Kulkarni',
    status: 'success', before_state: { role: 'viewer' }, after_state: { role: 'finance' }, ip_address: '203.0.113.24',
  },
];

function auditLogs(query: URLSearchParams): Paginated<AuditLogOut> {
  const entityType = query.get('entity_type');
  const items = entityType ? AUDIT_LOGS.filter((e) => e.entity_type === entityType) : AUDIT_LOGS;
  return { items, total: items.length, page: 1, page_size: 20, total_pages: 1 };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/audit-logs': auditLogs,
};
