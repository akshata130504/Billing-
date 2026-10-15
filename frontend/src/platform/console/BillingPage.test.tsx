import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  BillingPage as Page, CheckoutAttemptRow, NotificationPage, NotificationRow, PlatformSubscriptionRow, ReviewItem,
  ReviewQueuePage, WebhookEventRow,
} from '../billingApi';

const subscriptions = vi.fn();
const checkoutAttempts = vi.fn();
const webhookEvents = vi.fn();
const reviewQueue = vi.fn();
const resolveReviewCase = vi.fn();
const notifications = vi.fn();
vi.mock('../billingApi', () => ({
  PAGE_SIZE: 25,
  NOTIFICATION_KIND_LABELS: {
    subscription_activated: 'Plan activated (payment confirmed)',
    renewal_payment_received: 'Renewal payment received',
    payment_past_due: 'Renewal payment not confirmed',
    access_expired: 'Plan expired (read-only)',
    cancellation_scheduled: 'Cancellation scheduled',
    cancelled_immediately: 'Cancelled immediately',
    cancellation_effective: 'Plan ended as scheduled',
  },
  RESOLUTION_CATEGORY_LABELS: {
    no_action_needed: 'No action needed',
    resolved_by_payment_lifecycle: 'Resolved by the normal payment flow',
    handled_in_razorpay: 'Handled in the Razorpay dashboard',
    customer_contacted: 'Customer contacted',
    duplicate_case: 'Duplicate of another case',
    other: 'Other',
  },
  billingApi: {
    subscriptions: (p: unknown) => subscriptions(p),
    checkoutAttempts: (p: unknown) => checkoutAttempts(p),
    webhookEvents: (p: unknown) => webhookEvents(p),
    reviewQueue: (p: unknown) => reviewQueue(p),
    resolveReviewCase: (id: string, body: unknown) => resolveReviewCase(id, body),
    notifications: (p: unknown) => notifications(p),
  },
}));

import { PlatformApiError, platformApi } from '../platformApi';
import { NAV_ITEMS } from './ConsoleLayout';
import { BillingPage } from './BillingPage';

function page<T>(items: T[], total = items.length, pageNo = 1): Page<T> {
  return { items, total, page: pageNo, page_size: 25, total_pages: total ? Math.ceil(total / 25) : 0 };
}

function sub(overrides: Partial<PlatformSubscriptionRow> = {}): PlatformSubscriptionRow {
  return {
    organization_id: 'org-1', organization_name: 'Acme Pvt Ltd', plan_code: 'starter', plan_name: 'Starter', sandbox: false,
    state: 'active', effective_state: 'active', writable: true, cancel_at_period_end: false, billing_interval: 'month',
    billing_interval_count: 1, current_period_start: '2026-10-01T12:00:00Z', current_period_end: '2026-11-01T12:00:00Z',
    grace_period_end: null, cancelled_at: null, trial_ends_at: null, amount_minor: 79900, currency: 'INR',
    provider_subscription_id: 'sub_A1', provider_mode: 'test', provider_paid_count: 1, updated_at: '2026-10-01T12:00:00Z',
    ...overrides,
  };
}

function attempt(overrides: Partial<CheckoutAttemptRow> = {}): CheckoutAttemptRow {
  return {
    id: 'att-1', organization_id: 'org-1', organization_name: 'Acme Pvt Ltd', plan_code: 'starter', plan_name: 'Starter',
    sandbox: false, amount_minor: 79900, currency: 'INR', billing_interval: 'month', billing_interval_count: 1, seat_limit: 3,
    mode: 'test', status: 'created', provider_subscription_id: 'sub_A1', provider_payment_id: null,
    created_at: '2026-10-13T10:00:00Z', expires_at: '2026-10-13T10:30:00Z', authorized_at: null, completed_at: null,
    last_error: null, webhook_review: false, review_reason: null, review_flagged_at: null, stuck: false, ...overrides,
  };
}

function event(overrides: Partial<WebhookEventRow> = {}): WebhookEventRow {
  return {
    id: 'ev-1', event_id: 'evt_1', event_type: 'subscription.charged', mode: 'test', status: 'processed', outcome: 'renewed',
    provider_subscription_id: 'sub_A1', provider_payment_id: 'pay_1', organization_id: 'org-1', organization_name: 'Acme Pvt Ltd',
    event_created_at: '2026-10-13T10:00:00Z', received_at: '2026-10-13T10:00:05Z', ...overrides,
  };
}

function review(overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    source: 'checkout_review', explanation: 'A payment for this checkout could not be applied automatically.',
    detected_at: '2026-10-13T10:00:00Z', organization_id: 'org-1', organization_name: 'Acme Pvt Ltd',
    case_id: 'case-1', case_status: 'open', resolvable: true,
    first_reason: 'mismatch: captured payment amount or currency differs from the checkout',
    review_reason: 'mismatch: captured payment amount or currency differs from the checkout', finding_count: 1,
    flagged_at: '2026-10-13T10:00:00Z', last_seen_at: '2026-10-13T10:00:00Z', resolution_category: null,
    resolution_note: null, resolution_ticket_ref: null, resolved_at: null, resolved_by_email: null, resolved_by_role: null,
    checkout_status: 'created', outcome: 'mismatch', event_type: null, checkout_attempt_id: 'att-1',
    provider_subscription_id: 'sub_A1', provider_payment_id: 'pay_1', mode: 'test', ...overrides,
  };
}

function queue(items: ReviewItem[]): ReviewQueuePage {
  return { ...page(items), untracked_sources: [] };
}

const RESOLVED = review({
  case_status: 'resolved', resolvable: false, resolution_category: 'handled_in_razorpay',
  resolution_note: 'Refunded in the Razorpay dashboard after checking the amount.', resolution_ticket_ref: 'SUP-42',
  resolved_at: '2026-10-14T09:00:00Z', resolved_by_email: 'ops@rooman.test', resolved_by_role: 'platform_operations',
  finding_count: 2, review_reason: 'mismatch: subscription does not belong to this checkout',
});

async function openResolveDialog() {
  reviewQueue.mockResolvedValue(queue([review()]));
  renderPage();
  await openTab('Needs review');
  const row = await screen.findByTestId('review-row');
  await userEvent.click(within(row).getByRole('button', { name: 'Resolve' }));
  return screen.getByRole('form', { name: 'Resolve payment review' });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <BillingPage />
    </MemoryRouter>,
  );
}

async function openTab(name: string) {
  await userEvent.click(screen.getByRole('tab', { name }));
}

beforeEach(() => {
  subscriptions.mockReset().mockResolvedValue(page([]));
  checkoutAttempts.mockReset().mockResolvedValue(page([]));
  webhookEvents.mockReset().mockResolvedValue(page([]));
  reviewQueue.mockReset().mockResolvedValue({ ...page([]), untracked_sources: [] } satisfies ReviewQueuePage);
  resolveReviewCase.mockReset();
  notifications.mockReset().mockResolvedValue(emailPage([]));
});

describe('BillingPage', () => {
  it('shows a loading state while the first view loads', () => {
    subscriptions.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows the error from the server with a retry', async () => {
    subscriptions.mockRejectedValueOnce(new PlatformApiError('You do not have access to this.', 403, 'FORBIDDEN'));
    renderPage();
    expect(await screen.findByText('You do not have access to this.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again|retry/i }));
    await waitFor(() => expect(subscriptions).toHaveBeenCalledTimes(2));
  });

  it('shows an empty state for subscriptions', async () => {
    renderPage();
    expect(await screen.findByText('No subscriptions')).toBeInTheDocument();
    expect(subscriptions).toHaveBeenCalledWith({ status: 'paid', organization: '', page: 1 });
  });

  it('distinguishes subscription states and shows stored amounts', async () => {
    subscriptions.mockResolvedValue(page([
      sub(),
      sub({ organization_id: 'org-2', organization_name: 'Beta', cancel_at_period_end: true, provider_subscription_id: 'sub_B' }),
      sub({ organization_id: 'org-3', organization_name: 'Gamma', state: 'past_due', effective_state: 'past_due',
        grace_period_end: '2026-11-08T12:00:00Z', provider_subscription_id: 'sub_C' }),
      sub({ organization_id: 'org-4', organization_name: 'Delta', state: 'active', effective_state: 'past_due',
        provider_subscription_id: 'sub_D' }),
      sub({ organization_id: 'org-5', organization_name: 'Sandbox Co', plan_name: 'Sandbox Test Plan (Foundation)',
        sandbox: true, amount_minor: null, currency: null, provider_subscription_id: 'sub_E' }),
    ]));
    renderPage();
    const rows = await screen.findAllByTestId('subscription-row');
    expect(rows).toHaveLength(5);
    expect(within(rows[0]).getByText('Active')).toBeInTheDocument();
    expect(within(rows[0]).getByText('₹799.00')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Cancellation scheduled')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Past due')).toBeInTheDocument();
    expect(within(rows[2]).getByText(/Grace until/)).toBeInTheDocument();
    expect(within(rows[3]).getByText('Effective now: Past due')).toBeInTheDocument();
    expect(within(rows[4]).getByText('Test mode')).toBeInTheDocument();
    expect(within(rows[4]).getByText('—')).toBeInTheDocument(); // no stored amount: not invented
  });

  it('filters subscriptions by status and organization', async () => {
    renderPage();
    await screen.findByText('No subscriptions');
    await userEvent.click(screen.getByRole('tab', { name: 'Past due' }));
    await waitFor(() => expect(subscriptions).toHaveBeenLastCalledWith({ status: 'past_due', organization: '', page: 1 }));
    await userEvent.type(screen.getByLabelText('Organization name or id'), 'Acme');
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => expect(subscriptions).toHaveBeenLastCalledWith({ status: 'past_due', organization: 'Acme', page: 1 }));
  });

  it('pages through results', async () => {
    subscriptions.mockResolvedValue(page(Array.from({ length: 25 }, (_, i) => sub({ organization_id: `org-${i}` })), 30));
    renderPage();
    await screen.findAllByTestId('subscription-row');
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(subscriptions).toHaveBeenLastCalledWith({ status: 'paid', organization: '', page: 2 }));
  });

  it('marks checkout attempts that need attention', async () => {
    checkoutAttempts.mockResolvedValue(page([
      attempt({ id: 'a1', status: 'authorized', stuck: true, authorized_at: '2026-10-12T09:00:00Z' }),
      attempt({ id: 'a2', status: 'failed', last_error: 'Razorpay refused to start the checkout.' }),
      attempt({ id: 'a3', status: 'created', webhook_review: true }),
      attempt({ id: 'a4', status: 'completed', completed_at: '2026-10-13T10:05:00Z' }),
    ]));
    renderPage();
    await openTab('Checkout attempts');
    const rows = await screen.findAllByTestId('checkout-row');
    expect(within(rows[0]).getByText('Authorized, not charged')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Needs attention')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Failed')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Razorpay refused to start the checkout.')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Webhook needs review')).toBeInTheDocument();
    expect(within(rows[3]).getByText('Completed')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Key mode'), 'live');
    await waitFor(() => expect(checkoutAttempts).toHaveBeenLastCalledWith({ status: 'all', mode: 'live', organization: '', page: 1 }));
  });

  it('says plainly when the webhook ledger is empty', async () => {
    renderPage();
    await openTab('Webhook ledger');
    expect(await screen.findByText('The webhook ledger is empty')).toBeInTheDocument();
  });

  it('lists webhook events with their processing status', async () => {
    webhookEvents.mockResolvedValue(page([
      event(),
      event({ id: 'ev-2', event_id: 'evt_2', status: 'needs_review', outcome: 'mismatch' }),
      event({ id: 'ev-3', event_id: 'evt_3', status: 'ignored', outcome: 'unsupported_event', event_type: 'subscription.updated' }),
    ]));
    renderPage();
    await openTab('Webhook ledger');
    const rows = await screen.findAllByTestId('webhook-row');
    expect(within(rows[0]).getByText('Processed')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Needs review')).toBeInTheDocument();
    expect(within(rows[1]).getByText('mismatch')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Ignored')).toBeInTheDocument();
  });

  it('shows the review queue and states what it cannot list', async () => {
    reviewQueue.mockResolvedValue({
      ...page([
        review({ source: 'webhook_needs_review', explanation: 'A signed webhook could not be applied automatically (webhook ledger).',
          case_id: null, case_status: null, resolvable: false, first_reason: null, review_reason: null, finding_count: null,
          flagged_at: null, last_seen_at: null, checkout_status: null, event_type: 'subscription.charged', checkout_attempt_id: null }),
      ]),
      untracked_sources: ['Checkout callback reviews (PAYMENT_NEEDS_REVIEW) - logged and alerted only'],
    });
    renderPage();
    await openTab('Needs review');
    const row = await screen.findByTestId('review-row');
    expect(within(row).getByText('Webhook could not be applied')).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument(); // not a stored case
    expect(screen.getByTestId('untracked-sources')).toHaveTextContent('Checkout callback reviews');
  });

  it('shows an open payment review case with its findings and opening time', async () => {
    reviewQueue.mockResolvedValue(queue([review({ finding_count: 3, review_reason: 'mismatch: subscription does not belong to this checkout' })]));
    renderPage();
    await openTab('Needs review');
    const row = await screen.findByTestId('review-row');
    expect(within(row).getByText('Payment needs review')).toBeInTheDocument();
    expect(within(row).getByText('Open')).toBeInTheDocument();
    expect(row).toHaveTextContent('Latest finding: mismatch: subscription does not belong to this checkout');
    expect(row).toHaveTextContent('First finding: mismatch: captured payment amount or currency differs from the checkout');
    expect(row).toHaveTextContent('3 findings');
    expect(row).toHaveTextContent('checkout created');
    expect(within(row).getByRole('button', { name: 'Resolve' })).toBeInTheDocument();
    expect(screen.queryByTestId('untracked-sources')).not.toBeInTheDocument(); // nothing left untracked
  });

  it('defaults to open cases and filters resolved and all', async () => {
    renderPage();
    await openTab('Needs review');
    await waitFor(() => expect(reviewQueue).toHaveBeenLastCalledWith({ status: 'open', organization: '', page: 1 }));
    expect(screen.getByRole('tab', { name: 'Open' })).toHaveAttribute('aria-selected', 'true');
    reviewQueue.mockResolvedValue(queue([]));
    await openTab('Resolved');
    await waitFor(() => expect(reviewQueue).toHaveBeenLastCalledWith({ status: 'resolved', organization: '', page: 1 }));
    expect(await screen.findByText('No resolved cases')).toBeInTheDocument();
    await openTab('All');
    await waitFor(() => expect(reviewQueue).toHaveBeenLastCalledWith({ status: 'all', organization: '', page: 1 }));
    await userEvent.type(screen.getByLabelText('Organization name or id'), 'Acme');
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => expect(reviewQueue).toHaveBeenLastCalledWith({ status: 'all', organization: 'Acme', page: 1 }));
  });

  it('shows who resolved a case, when, how and why, without a resolve action', async () => {
    reviewQueue.mockResolvedValue(queue([RESOLVED]));
    renderPage();
    await openTab('Needs review');
    await openTab('Resolved');
    const row = await screen.findByTestId('review-row');
    const resolution = within(row).getByTestId('review-resolution');
    expect(within(row).getByText('Resolved')).toBeInTheDocument();
    expect(resolution).toHaveTextContent('Handled in the Razorpay dashboard');
    expect(resolution).toHaveTextContent('ops@rooman.test (platform operations)');
    expect(resolution).toHaveTextContent('SUP-42');
    expect(resolution).toHaveTextContent('Refunded in the Razorpay dashboard after checking the amount.');
    expect(row).toHaveTextContent('First finding: mismatch: captured payment amount'); // the original reason is kept
    expect(within(row).queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument();
  });

  it('requires a category and an explanation before resolving, and says it changes no payment', async () => {
    const form = await openResolveDialog();
    expect(form).toHaveTextContent('It does not approve, refund, retry or change any payment.');
    const confirm = within(form).getByRole('button', { name: 'Resolve review' });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(form).getByLabelText(/What did you investigate/), 'Checked the payment carefully.');
    expect(confirm).toBeDisabled(); // no category yet
    await userEvent.selectOptions(within(form).getByLabelText(/Resolution/), 'handled_in_razorpay');
    expect(confirm).toBeEnabled();
    await userEvent.clear(within(form).getByLabelText(/What did you investigate/));
    await userEvent.type(within(form).getByLabelText(/What did you investigate/), 'too short');
    expect(confirm).toBeDisabled();
    expect(resolveReviewCase).not.toHaveBeenCalled();
  });

  it('resolves a case after a password step-up and refreshes the list', async () => {
    resolveReviewCase
      .mockRejectedValueOnce(new PlatformApiError('Confirm your password.', 403, 'STEP_UP_REQUIRED'))
      .mockResolvedValueOnce(RESOLVED);
    const stepUp = vi.spyOn(platformApi, 'stepUp').mockResolvedValue(undefined as never);
    const form = await openResolveDialog();
    await userEvent.selectOptions(within(form).getByLabelText(/Resolution/), 'handled_in_razorpay');
    await userEvent.type(within(form).getByLabelText(/What did you investigate/), 'Refunded in the Razorpay dashboard.');
    await userEvent.type(within(form).getByLabelText(/Ticket reference/), 'SUP-42');
    reviewQueue.mockClear().mockResolvedValue(queue([]));
    await userEvent.click(within(form).getByRole('button', { name: 'Resolve review' }));
    const password = await screen.findByLabelText(/^Password/);
    await userEvent.type(password, 'correct horse');
    await userEvent.click(screen.getByRole('button', { name: 'Verify and resolve review' }));
    await waitFor(() => expect(resolveReviewCase).toHaveBeenCalledTimes(2));
    expect(stepUp).toHaveBeenCalledWith('correct horse');
    expect(resolveReviewCase).toHaveBeenLastCalledWith('case-1', {
      category: 'handled_in_razorpay', reason: 'Refunded in the Razorpay dashboard.', ticket_ref: 'SUP-42' });
    await waitFor(() => expect(reviewQueue).toHaveBeenCalled()); // refreshed
    expect(await screen.findByText('Nothing needs review')).toBeInTheDocument();
    stepUp.mockRestore();
  });

  it('shows the server error when a case was already resolved', async () => {
    resolveReviewCase.mockRejectedValue(new PlatformApiError('This review case is already resolved.', 409, 'REVIEW_ALREADY_RESOLVED'));
    const form = await openResolveDialog();
    await userEvent.selectOptions(within(form).getByLabelText(/Resolution/), 'no_action_needed');
    await userEvent.type(within(form).getByLabelText(/What did you investigate/), 'Investigated and nothing is needed.');
    await userEvent.click(within(form).getByRole('button', { name: 'Resolve review' }));
    expect(await within(form).findByRole('alert')).toHaveTextContent('This review case is already resolved.');
  });

  it('marks a flagged checkout attempt with its review reason', async () => {
    checkoutAttempts.mockResolvedValue(page([
      attempt({ review_reason: 'needs_review: plan is no longer sold on the terms of this checkout',
        review_flagged_at: '2026-10-13T10:00:00Z' }),
    ]));
    renderPage();
    await openTab('Checkout attempts');
    const [row] = await screen.findAllByTestId('checkout-row');
    expect(within(row).getByText('Needs review')).toBeInTheDocument();
    expect(row).toHaveTextContent('needs_review: plan is no longer sold on the terms of this checkout');
  });

  it('shows an empty review queue', async () => {
    renderPage();
    await openTab('Needs review');
    expect(await screen.findByText('Nothing needs review')).toBeInTheDocument();
  });

  it('offers no actions: the console is read-only', async () => {
    subscriptions.mockResolvedValue(page([sub()]));
    renderPage();
    await screen.findAllByTestId('subscription-row');
    const buttons = screen.getAllByRole('button').map((b) => b.textContent ?? '');
    expect(buttons.some((t) => /cancel|approve|refund|replay|retry payment|grant/i.test(t))).toBe(false);
  });
});

function email(overrides: Partial<NotificationRow> = {}): NotificationRow {
  return {
    id: 'n-1', kind: 'payment_past_due', status: 'pending', attempts: 0, organization_id: 'org-1',
    organization_name: 'Acme Pvt Ltd', recipient_hint: 'o***@acme.example', created_at: '2026-10-14T10:00:00Z',
    updated_at: '2026-10-14T10:00:00Z', sent_at: null, next_attempt_at: null, error_code: null, error_label: null,
    ...overrides,
  };
}

function emailPage(items: NotificationRow[], counts = { pending: 0, sent: 0, failed: 0, superseded: 0 }): NotificationPage {
  return { ...page(items), status_counts: counts };
}

describe('Email delivery', () => {
  async function openEmail() {
    renderPage();
    await openTab('Email delivery');
  }

  it('shows a loading state', async () => {
    notifications.mockReturnValue(new Promise(() => undefined));
    await openEmail();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows the server error with a retry', async () => {
    notifications.mockRejectedValueOnce(new PlatformApiError('You do not have access to this.', 403, 'FORBIDDEN'));
    await openEmail();
    expect(await screen.findByText('You do not have access to this.')).toBeInTheDocument();
    notifications.mockResolvedValue(emailPage([]));
    await userEvent.click(screen.getByRole('button', { name: /try again|retry/i }));
    expect(await screen.findByText('No emails yet')).toBeInTheDocument();
  });

  it('shows an empty state, and a different one when filters match nothing', async () => {
    await openEmail();
    expect(await screen.findByText('No emails yet')).toBeInTheDocument();
    await openTab('Failed');
    expect(await screen.findByText('No matching emails')).toBeInTheDocument();
  });

  it('lists delivery records with status, attempts, retry time and a safe error - but no content', async () => {
    notifications.mockResolvedValue(emailPage([
      email({ id: 'n-1', status: 'failed', attempts: 8, error_code: 'smtp_timeout',
        error_label: 'The SMTP server did not answer in time' }),
      email({ id: 'n-2', status: 'pending', attempts: 2, error_code: 'smtp_unreachable',
        error_label: 'The SMTP server could not be reached', next_attempt_at: '2026-10-14T11:00:00Z' }),
      email({ id: 'n-3', kind: 'subscription_activated', status: 'sent', attempts: 1, sent_at: '2026-10-14T10:01:00Z' }),
      email({ id: 'n-4', kind: 'access_expired', status: 'superseded', error_code: 'no_longer_applicable',
        error_label: 'Not sent: no longer true when its turn came' }),
    ], { pending: 1, sent: 1, failed: 1, superseded: 1 }));
    await openEmail();
    const rows = await screen.findAllByTestId('email-row');
    expect(rows).toHaveLength(4);
    expect(within(rows[0]).getByText('Failed')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Renewal payment not confirmed')).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent('The SMTP server did not answer in time');
    expect(rows[0]).toHaveTextContent('8');
    expect(rows[0]).not.toHaveTextContent('Next attempt');
    expect(rows[1]).toHaveTextContent('Next attempt');
    expect(within(rows[2]).getByText('Sent to SMTP')).toBeInTheDocument();
    expect(rows[2]).toHaveTextContent('Plan activated (payment confirmed)');
    expect(within(rows[3]).getByText('Not sent (superseded)')).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent('To o***@acme.example');
    expect(screen.getByTestId('email-status-counts')).toHaveTextContent('1 failed · 1 pending · 1 sent to SMTP · 1 superseded');
    // "sent" is explained as accepted by SMTP, not as inbox delivery
    expect(screen.getByText(/does not prove it reached or was read/)).toBeInTheDocument();
    // read-only: no actions
    const actions = screen.getAllByRole('button').map((b) => b.textContent ?? '');
    expect(actions.some((t) => /resend|retry now|delete|resolve/i.test(t))).toBe(false);
  });

  it('filters by status, email type and organization on the server', async () => {
    await openEmail();
    await waitFor(() => expect(notifications).toHaveBeenLastCalledWith({ status: 'all', kind: '', organization: '', page: 1 }));
    await openTab('Failed');
    await waitFor(() => expect(notifications).toHaveBeenLastCalledWith({ status: 'failed', kind: '', organization: '', page: 1 }));
    await userEvent.selectOptions(screen.getByLabelText('Email type'), 'payment_past_due');
    await waitFor(() => expect(notifications).toHaveBeenLastCalledWith({
      status: 'failed', kind: 'payment_past_due', organization: '', page: 1 }));
    await userEvent.type(screen.getByLabelText('Organization name or id'), 'Acme');
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => expect(notifications).toHaveBeenLastCalledWith({
      status: 'failed', kind: 'payment_past_due', organization: 'Acme', page: 1 }));
  });

  it('pages through results', async () => {
    notifications.mockResolvedValue({ ...emailPage([email()]), total: 60, total_pages: 3 });
    await openEmail();
    await screen.findAllByTestId('email-row');
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(notifications).toHaveBeenLastCalledWith({ status: 'all', kind: '', organization: '', page: 2 }));
  });
});

describe('Plan billing navigation', () => {
  it('is offered to Administrators and Operations, not Support', () => {
    const item = NAV_ITEMS.find((n) => n.to === '/billing');
    expect(item?.roles).toEqual(['platform_administrator', 'platform_operations']);
  });
});
