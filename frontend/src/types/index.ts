export interface DatabaseHealth {
  status: 'connected' | 'disconnected';
  dialect: string;
  url_masked?: string;
  error?: string;
}

export interface HealthResponse {
  status: string;
  project_name: string;
  version: string;
  timestamp: string;
  environment: string;
  database: DatabaseHealth;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiResponse<T> {
  data?: T;
  error?: ApiError;
}

// Navigation Item Definition
export interface NavigationItem {
  title: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export interface NavigationSection {
  title: string;
  items: NavigationItem[];
}

// Date Range Filter Options
export type DateRangeFilter =
  | 'today'
  | '7_days'
  | '30_days'
  | '3_months'
  | '12_months'
  | 'custom';

// Dashboard Widget Toggle Configuration
export interface WidgetVisibilityState {
  revenueIntelligence: boolean;
  actionCenter: boolean;
  billingPipeline: boolean;
  customerHealth: boolean;
  paymentRecovery: boolean;
  recentTransactions: boolean;
  activityTimeline: boolean;
}

// Activity Item Definition
export type ActivityCategory = 'all' | 'billing' | 'customers' | 'payments' | 'system';

export interface ActivityItem {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  category: 'billing' | 'customers' | 'payments' | 'system';
  severity?: 'normal' | 'warning' | 'danger' | 'success';
}

// Search Result Item
export type SearchCategory =
  | 'customers'
  | 'invoices'
  | 'quotes'
  | 'products'
  | 'subscriptions'
  | 'payments';

export interface SearchResultItem {
  id: string;
  category: SearchCategory;
  title: string;
  subtitle: string;
  path: string;
  badge?: string;
}
