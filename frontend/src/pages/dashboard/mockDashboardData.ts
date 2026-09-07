import { ActivityItem, SearchResultItem } from '../../types';

export interface DashboardMetric {
  title: string;
  value: string;
  change: string;
  isPositive: boolean;
  comparisonText: string;
}

export const mockDashboardMetrics: DashboardMetric[] = [
  {
    title: 'Total Revenue',
    value: '₹1,248,500.00',
    change: '+14.8%',
    isPositive: true,
    comparisonText: 'vs prior period',
  },
  {
    title: 'Outstanding Invoices',
    value: '₹142,650.00',
    change: '-3.2%',
    isPositive: true, // Drop in outstanding is positive
    comparisonText: '12 unpaid (4 overdue)',
  },
  {
    title: 'Active Customers',
    value: '1,420',
    change: '+38',
    isPositive: true,
    comparisonText: '98.2% retention rate',
  },
  {
    title: 'At-Risk Revenue',
    value: '₹36,400.00',
    change: '+2.1%',
    isPositive: false,
    comparisonText: '5 accounts in grace period',
  },
];

// Revenue Intelligence
export interface RevenueIntelligenceData {
  mrr: string;
  mrrChange: string;
  arr: string;
  arrChange: string;
  growthRate: string;
  forecastedRevenue: string;
  trend: { label: string; actual: number; forecast: number }[];
}

export const mockRevenueIntelligence: RevenueIntelligenceData = {
  mrr: '₹104,200.00',
  mrrChange: '+12.4% MoM',
  arr: '₹1,250,400.00',
  arrChange: '+18.6% YoY',
  growthRate: '18.6%',
  forecastedRevenue: '₹1,380,000.00',
  trend: [
    { label: 'Jan', actual: 65, forecast: 65 },
    { label: 'Feb', actual: 72, forecast: 70 },
    { label: 'Mar', actual: 78, forecast: 76 },
    { label: 'Apr', actual: 85, forecast: 82 },
    { label: 'May', actual: 92, forecast: 90 },
    { label: 'Jun', actual: 98, forecast: 95 },
    { label: 'Jul', actual: 94, forecast: 100 },
    { label: 'Aug', actual: 101, forecast: 105 },
    { label: 'Sep', actual: 108, forecast: 110 },
    { label: 'Oct', actual: 115, forecast: 118 },
    { label: 'Nov', actual: 122, forecast: 125 },
    { label: 'Dec', actual: 130, forecast: 132 },
  ],
};

// Action Center Items
export interface ActionCenterItem {
  id: string;
  category: 'overdue' | 'failed_payment' | 'expiring_trial' | 'pending_quote';
  title: string;
  description: string;
  amount?: string;
  dueDate?: string;
  account: string;
}

export const mockActionCenterItems: ActionCenterItem[] = [
  {
    id: 'ac-1',
    category: 'overdue',
    title: 'Invoice #INV-2026-0087 Overdue (14 days)',
    description: 'Hyperion FinTech Ltd has not cleared invoice after 2 automated reminders.',
    amount: '₹42,000.00',
    dueDate: 'Sep 05, 2026',
    account: 'Hyperion FinTech Ltd',
  },
  {
    id: 'ac-2',
    category: 'failed_payment',
    title: 'Card Payment Failed on Stripe Checkout',
    description: 'Insufficient funds reported for Solaria Robotics annual renewal.',
    amount: '₹18,500.00',
    account: 'Solaria Robotics Corp',
  },
  {
    id: 'ac-3',
    category: 'expiring_trial',
    title: 'Enterprise Trial Expiring in 24 Hours',
    description: 'Vanguard Biometrics completed 13/14 trial days. Ready for conversion.',
    account: 'Vanguard Biometrics',
  },
  {
    id: 'ac-4',
    category: 'pending_quote',
    title: 'Quote #QT-2026-0034 Awaiting Client Approval',
    description: 'Custom tiered plan quote sent to Nexus Global Logistics awaiting e-sign.',
    amount: '₹84,000.00',
    account: 'Nexus Global Logistics',
  },
];

// Billing Pipeline Stages
export interface PipelineStage {
  stage: 'quote' | 'invoice' | 'payment' | 'paid';
  title: string;
  count: number;
  monetaryValue: string;
  description: string;
}

export const mockBillingPipeline: PipelineStage[] = [
  {
    stage: 'quote',
    title: 'Quote',
    count: 14,
    monetaryValue: '₹168,000.00',
    description: 'Drafted & sent proposals',
  },
  {
    stage: 'invoice',
    title: 'Invoice',
    count: 28,
    monetaryValue: '₹312,400.00',
    description: 'Issued & pending collection',
  },
  {
    stage: 'payment',
    title: 'Payment',
    count: 18,
    monetaryValue: '₹196,800.00',
    description: 'Initiated & settlement queues',
  },
  {
    stage: 'paid',
    title: 'Paid',
    count: 142,
    monetaryValue: '₹1,051,700.00',
    description: 'Fully reconciled revenue',
  },
];

// Customer Health Distribution
export interface CustomerHealthStats {
  healthy: { count: number; percentage: number; mrr: string };
  needsAttention: { count: number; percentage: number; mrr: string };
  atRisk: { count: number; percentage: number; mrr: string };
  churned: { count: number; percentage: number; mrr: string };
}

export const mockCustomerHealth: CustomerHealthStats = {
  healthy: { count: 1180, percentage: 83, mrr: '₹88,200.00' },
  needsAttention: { count: 142, percentage: 10, mrr: '₹10,500.00' },
  atRisk: { count: 68, percentage: 5, mrr: '₹4,100.00' },
  churned: { count: 30, percentage: 2, mrr: '₹1,400.00' },
};

// Payment Recovery
export interface PaymentRecoveryStats {
  failedPaymentsAmount: string;
  failedCount: number;
  retryScheduledAmount: string;
  retryCount: number;
  recoveredPaymentsAmount: string;
  recoveredCount: number;
  recoveryRate: string;
  rateImprovement: string;
}

export const mockPaymentRecovery: PaymentRecoveryStats = {
  failedPaymentsAmount: '₹42,800.00',
  failedCount: 16,
  retryScheduledAmount: '₹28,600.00',
  retryCount: 11,
  recoveredPaymentsAmount: '₹31,400.00',
  recoveredCount: 12,
  recoveryRate: '73.4%',
  rateImprovement: '+5.2% vs last cycle',
};

// Recent Transactions
export interface TransactionItem {
  id: string;
  txHash: string;
  customerName: string;
  invoiceNumber: string;
  amount: string;
  paymentMethod: string;
  date: string;
  status: 'settled' | 'processing' | 'refunded' | 'failed';
}

export const mockRecentTransactions: TransactionItem[] = [
  {
    id: 'tx-1',
    txHash: 'TXN-984210',
    customerName: 'Acme Cloud Dynamics',
    invoiceNumber: 'INV-2026-0089',
    amount: '₹34,000.00',
    paymentMethod: 'Credit Card (Stripe)',
    date: 'Sep 07, 2026 • 13:45',
    status: 'settled',
  },
  {
    id: 'tx-2',
    txHash: 'TXN-984209',
    customerName: 'Solaria Robotics Corp',
    invoiceNumber: 'INV-2026-0086',
    amount: '₹9,500.00',
    paymentMethod: 'UPI Auto-Debit',
    date: 'Sep 07, 2026 • 11:20',
    status: 'settled',
  },
  {
    id: 'tx-3',
    txHash: 'TXN-984208',
    customerName: 'Nexus Global Logistics',
    invoiceNumber: 'INV-2026-0088',
    amount: '₹18,500.00',
    paymentMethod: 'Net Banking NEFT',
    date: 'Sep 06, 2026 • 16:30',
    status: 'processing',
  },
  {
    id: 'tx-4',
    txHash: 'TXN-984207',
    customerName: 'Hyperion FinTech Ltd',
    invoiceNumber: 'INV-2026-0084',
    amount: '₹42,000.00',
    paymentMethod: 'Corporate ACH',
    date: 'Sep 06, 2026 • 09:15',
    status: 'failed',
  },
  {
    id: 'tx-5',
    txHash: 'TXN-984206',
    customerName: 'Vanguard Biometrics',
    invoiceNumber: 'INV-2026-0081',
    amount: '₹5,200.00',
    paymentMethod: 'Credit Card',
    date: 'Sep 05, 2026 • 14:02',
    status: 'refunded',
  },
];

// Activity Timeline with Categories
export const mockActivityTimeline: ActivityItem[] = [
  {
    id: 'act-1',
    title: 'Payment Reconciled (₹34,000.00)',
    description: 'Stripe webhook verified payment for Invoice #INV-2026-0089 (Acme Cloud Dynamics).',
    timestamp: '18 mins ago',
    category: 'payments',
    severity: 'success',
  },
  {
    id: 'act-2',
    title: 'New Enterprise Subscription Activated',
    description: 'Solaria Robotics converted from trial to Enterprise Annual Tier (12 seats).',
    timestamp: '2 hours ago',
    category: 'billing',
    severity: 'normal',
  },
  {
    id: 'act-3',
    title: 'New Customer Lead Onboarded',
    description: 'Apex Cloud Solutions added to customer directory via self-serve portal sign-up.',
    timestamp: '4 hours ago',
    category: 'customers',
    severity: 'normal',
  },
  {
    id: 'act-4',
    title: 'Smart Dunning Retry Scheduled',
    description: 'Auto-retry rule triggered for Hyperion FinTech Ltd (Retry #2 of 3 scheduled in 48h).',
    timestamp: '6 hours ago',
    category: 'payments',
    severity: 'warning',
  },
  {
    id: 'act-5',
    title: 'System Automated Billing Run Completed',
    description: 'Recurring billing engine successfully generated 28 cycle invoices with 0 errors.',
    timestamp: '1 day ago',
    category: 'system',
    severity: 'normal',
  },
  {
    id: 'act-6',
    title: 'Quote #QT-2026-0034 Formally Accepted',
    description: 'Nexus Global Logistics accepted enterprise quote. Automated invoice drafting queued.',
    timestamp: '1 day ago',
    category: 'billing',
    severity: 'success',
  },
];

// Global Search Directory Mock
export const mockSearchDirectory: SearchResultItem[] = [
  // Customers
  {
    id: 's-c1',
    category: 'customers',
    title: 'Acme Cloud Dynamics',
    subtitle: 'Enterprise Customer • Bangalore, IN',
    path: '/customers',
    badge: 'Active',
  },
  {
    id: 's-c2',
    category: 'customers',
    title: 'Hyperion FinTech Ltd',
    subtitle: 'Scale Tier • Mumbai, IN',
    path: '/customers',
    badge: 'Past Due',
  },
  {
    id: 's-c3',
    category: 'customers',
    title: 'Solaria Robotics Corp',
    subtitle: 'Pro Annual • Hyderabad, IN',
    path: '/customers',
    badge: 'Active',
  },
  // Invoices
  {
    id: 's-i1',
    category: 'invoices',
    title: 'INV-2026-0089',
    subtitle: 'Acme Cloud Dynamics • ₹34,000.00',
    path: '/revenue/invoices',
    badge: 'Paid',
  },
  {
    id: 's-i2',
    category: 'invoices',
    title: 'INV-2026-0087',
    subtitle: 'Hyperion FinTech Ltd • ₹42,000.00',
    path: '/revenue/invoices',
    badge: 'Overdue',
  },
  // Quotes
  {
    id: 's-q1',
    category: 'quotes',
    title: 'QT-2026-0034',
    subtitle: 'Nexus Global Logistics • ₹84,000.00',
    path: '/revenue/quotes',
    badge: 'Accepted',
  },
  {
    id: 's-q2',
    category: 'quotes',
    title: 'QT-2026-0035',
    subtitle: 'Orion Systems Pvt Ltd • ₹56,000.00',
    path: '/revenue/quotes',
    badge: 'Sent',
  },
  // Products
  {
    id: 's-p1',
    category: 'products',
    title: 'Enterprise Billing Core',
    subtitle: 'Recurring Plan • ₹48,000/mo',
    path: '/catalog',
    badge: 'Plan',
  },
  {
    id: 's-p2',
    category: 'products',
    title: 'High-Volume API Meter Metering Pack',
    subtitle: 'Usage Add-on • ₹0.05/call',
    path: '/catalog',
    badge: 'Add-on',
  },
  // Subscriptions
  {
    id: 's-sub1',
    category: 'subscriptions',
    title: 'SUB-2026-0142',
    subtitle: 'Acme Cloud Dynamics • Enterprise Tier',
    path: '/subscriptions/all',
    badge: 'Active',
  },
  // Payments
  {
    id: 's-pay1',
    category: 'payments',
    title: 'TXN-984210',
    subtitle: '₹34,000.00 via Stripe • Settled',
    path: '/revenue/payments',
    badge: 'Settled',
  },
];
