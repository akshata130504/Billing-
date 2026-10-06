/**
 * Visual-editor preview sample data for the Activity feed (/activity). Fictional.
 * Timestamps are relative to "now" so the feed shows its Today / Yesterday / dated groups.
 */
import type { ActivityItem, Paginated } from '../../../types/api';

const HOUR = 3_600_000;

const SEEDS: Array<Omit<ActivityItem, 'timestamp'> & { hoursAgo: number }> = [
  { id: 'act-1', hoursAgo: 1, title: 'Invoice sent', description: 'INV-1048 - Asha Sharma', category: 'billing', severity: 'normal', entity_type: 'invoice', entity_id: '00000000-0000-4000-b000-000000001048' },
  { id: 'act-2', hoursAgo: 2, title: 'Payment received', description: 'PAY-0212 - Ravi Menon', category: 'payments', severity: 'success', entity_type: 'payment', entity_id: '00000000-0000-4000-c000-000000000212' },
  { id: 'act-3', hoursAgo: 4, title: 'Customer created', description: 'Saffron Studio - Asha Sharma', category: 'customers', severity: 'normal', entity_type: 'customer', entity_id: '00000000-0000-4000-a000-000000000006' },
  { id: 'act-4', hoursAgo: 27, title: 'Payment failed', description: 'PAY-0209 - Card gateway', category: 'payments', severity: 'danger', entity_type: 'payment', entity_id: '00000000-0000-4000-c000-000000000209' },
  { id: 'act-5', hoursAgo: 30, title: 'Quote approved', description: 'QT-0031 - Meera Iyer', category: 'billing', severity: 'success', entity_type: 'quote', entity_id: '00000000-0000-4000-d000-000000000031' },
  { id: 'act-6', hoursAgo: 52, title: 'Invoice overdue', description: 'INV-1041', category: 'billing', severity: 'warning', entity_type: 'invoice', entity_id: '00000000-0000-4000-b000-000000001041' },
  { id: 'act-7', hoursAgo: 75, title: 'Team member invited', description: 'ops@example.com - Asha Sharma', category: 'system', severity: 'normal', entity_type: 'membership', entity_id: null },
];

function listActivity(query: URLSearchParams): Paginated<ActivityItem> {
  const now = Date.now();
  const category = query.get('category');
  const items: ActivityItem[] = SEEDS.filter((s) => !category || category === 'all' || s.category === category).map(
    ({ hoursAgo, ...item }) => ({ ...item, timestamp: new Date(now - hoursAgo * HOUR).toISOString() })
  );
  const pageSize = Number(query.get('page_size')) || 25;
  const page = Number(query.get('page')) || 1;
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    total: items.length,
    page,
    page_size: pageSize,
    total_pages: Math.max(1, Math.ceil(items.length / pageSize)),
  };
}

export const routes: Record<string, (query: URLSearchParams) => unknown> = {
  '/activity': listActivity,
};
