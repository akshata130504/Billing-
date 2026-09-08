/**
 * Shared React Query key factories. Every page builder should derive keys from
 * here so invalidation stays consistent across modules.
 *
 * Convention: `[domain]` invalidates everything in a domain,
 * `[domain, 'list', params]` a specific list, `[domain, 'detail', id]` one row.
 */
export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    me: () => ['auth', 'me'] as const,
    invitation: (token: string) => ['auth', 'invitation', token] as const,
  },
  organization: {
    all: ['organization'] as const,
    detail: () => ['organization', 'detail'] as const,
    team: () => ['organization', 'team'] as const,
  },
  meta: {
    integrations: () => ['meta', 'integrations'] as const,
    health: () => ['meta', 'health'] as const,
  },
  customers: {
    all: ['customers'] as const,
    list: (params?: object) => ['customers', 'list', params ?? {}] as const,
    detail: (id: string) => ['customers', 'detail', id] as const,
    invoices: (id: string, params?: object) => ['customers', 'detail', id, 'invoices', params ?? {}] as const,
    payments: (id: string, params?: object) => ['customers', 'detail', id, 'payments', params ?? {}] as const,
    subscriptions: (id: string, params?: object) =>
      ['customers', 'detail', id, 'subscriptions', params ?? {}] as const,
  },
  catalog: {
    all: ['catalog'] as const,
    products: (params?: object) => ['catalog', 'products', params ?? {}] as const,
    product: (id: string) => ['catalog', 'product', id] as const,
    plans: (params?: object) => ['catalog', 'plans', params ?? {}] as const,
    plan: (id: string) => ['catalog', 'plan', id] as const,
  },
  quotes: {
    all: ['quotes'] as const,
    list: (params?: object) => ['quotes', 'list', params ?? {}] as const,
    detail: (id: string) => ['quotes', 'detail', id] as const,
  },
  subscriptions: {
    all: ['subscriptions'] as const,
    list: (params?: object) => ['subscriptions', 'list', params ?? {}] as const,
    detail: (id: string) => ['subscriptions', 'detail', id] as const,
    invoices: (id: string, params?: object) => ['subscriptions', 'detail', id, 'invoices', params ?? {}] as const,
  },
  invoices: {
    all: ['invoices'] as const,
    list: (params?: object) => ['invoices', 'list', params ?? {}] as const,
    detail: (id: string) => ['invoices', 'detail', id] as const,
  },
  payments: {
    all: ['payments'] as const,
    list: (params?: object) => ['payments', 'list', params ?? {}] as const,
    detail: (id: string) => ['payments', 'detail', id] as const,
    reconciliationSummary: () => ['payments', 'reconciliation-summary'] as const,
  },
  collections: {
    all: ['collections'] as const,
    dashboard: () => ['collections', 'dashboard'] as const,
    list: (params?: object) => ['collections', 'list', params ?? {}] as const,
    detail: (id: string) => ['collections', 'detail', id] as const,
  },
  controlCenter: {
    all: ['control-center'] as const,
    dashboard: (range: string) => ['control-center', 'dashboard', range] as const,
    actionCenter: () => ['control-center', 'action-center'] as const,
    calendar: (month: string) => ['control-center', 'calendar', month] as const,
    approvals: (params?: object) => ['control-center', 'approvals', params ?? {}] as const,
    auditLogs: (params?: object) => ['control-center', 'audit-logs', params ?? {}] as const,
    activity: (params?: object) => ['control-center', 'activity', params ?? {}] as const,
    search: (q: string) => ['control-center', 'search', q] as const,
    imports: (params?: object) => ['control-center', 'imports', params ?? {}] as const,
  },
  reports: {
    all: ['reports'] as const,
    dashboard: (params?: object) => ['reports', 'dashboard', params ?? {}] as const,
    revenue: (params?: object) => ['reports', 'revenue', params ?? {}] as const,
    receivables: (params?: object) => ['reports', 'receivables', params ?? {}] as const,
    invoices: (params?: object) => ['reports', 'invoices', params ?? {}] as const,
    payments: (params?: object) => ['reports', 'payments', params ?? {}] as const,
    customers: (params?: object) => ['reports', 'customers', params ?? {}] as const,
    products: (params?: object) => ['reports', 'products', params ?? {}] as const,
  },
  public: {
    invoice: (token: string) => ['public', 'invoice', token] as const,
    quote: (token: string) => ['public', 'quote', token] as const,
  },
  automation: {
    all: ['automation'] as const,
    dashboard: () => ['automation', 'dashboard'] as const,
    rules: (params?: object) => ['automation', 'rules', params ?? {}] as const,
    executions: (params?: object) => ['automation', 'executions', params ?? {}] as const,
  },
} as const;

/**
 * Keys that any invoice/payment mutation should invalidate together, because
 * the server recomputes invoice amounts, dashboards and action items.
 */
export const financialInvalidationKeys = [
  queryKeys.invoices.all,
  queryKeys.payments.all,
  queryKeys.subscriptions.all,
  queryKeys.customers.all,
  queryKeys.controlCenter.all,
] as const;
