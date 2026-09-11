import { useState } from 'react';
import { Save, AlertCircle } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { cn } from '../../utils/cn';
import { SettingsSection } from './settingsShared';

const NOTIFICATIONS_STORAGE_KEY = 'rooman_notification_preferences';

export interface NotificationPreferences {
  // Billing
  paymentReceived: boolean;
  paymentFailed: boolean;
  invoiceCreated: boolean;
  invoiceOverdue: boolean;
  invoicePaid: boolean;
  refundProcessed: boolean;

  // Subscription
  subscriptionCreated: boolean;
  subscriptionUpgraded: boolean;
  subscriptionDowngraded: boolean;
  subscriptionCancelled: boolean;
  trialEnding: boolean;
  trialExpired: boolean;

  // Customer Activity
  newCustomer: boolean;
  customerPortalActivity: boolean;
  paymentMethodChanges: boolean;

  // System
  systemAlerts: boolean;
  serviceNotifications: boolean;
  securityAlerts: boolean;

  // Delivery channels
  emailNotifications: boolean;
  inAppNotifications: boolean;
}

const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  paymentReceived: true,
  paymentFailed: true,
  invoiceCreated: false,
  invoiceOverdue: true,
  invoicePaid: true,
  refundProcessed: true,

  subscriptionCreated: true,
  subscriptionUpgraded: true,
  subscriptionDowngraded: true,
  subscriptionCancelled: true,
  trialEnding: true,
  trialExpired: true,

  newCustomer: true,
  customerPortalActivity: false,
  paymentMethodChanges: true,

  systemAlerts: true,
  serviceNotifications: true,
  securityAlerts: true,

  emailNotifications: true,
  inAppNotifications: true,
};

function loadNotifications(): NotificationPreferences {
  try {
    const raw = localStorage.getItem(NOTIFICATIONS_STORAGE_KEY);
    return raw ? { ...DEFAULT_NOTIFICATIONS, ...JSON.parse(raw) } : DEFAULT_NOTIFICATIONS;
  } catch {
    return DEFAULT_NOTIFICATIONS;
  }
}

function saveNotifications(prefs: NotificationPreferences) {
  try {
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Storage unavailable
  }
}

interface ToggleItemProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function ToggleItem({ label, description, checked, onChange }: ToggleItemProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-slate-100 last:border-0">
      <div className="space-y-0.5">
        <p className="text-xs font-semibold text-slate-800">{label}</p>
        <p className="text-[11px] text-slate-400 leading-normal">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2',
          checked ? 'bg-brand-600' : 'bg-slate-200'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out',
            checked ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </button>
    </div>
  );
}

export function NotificationsTab() {
  const { showToast } = useToast();
  const [prefs, setPrefs] = useState<NotificationPreferences>(loadNotifications);
  const [isSaving, setIsSaving] = useState(false);

  const update = <K extends keyof NotificationPreferences>(key: K, value: NotificationPreferences[K]) => {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      saveNotifications(prefs);
      // These choices are stored in this browser. The server does not yet read
      // them when deciding what to send, so the message must not promise that
      // outgoing email has changed.
      showToast(
        'success',
        'Preferences saved on this device',
        'In-app alerts now follow these choices. Emails sent by the server are not filtered by them yet.'
      );
    } catch {
      showToast('error', 'Save failed', 'Could not save notification preferences.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-100 rounded-lg text-xs text-amber-800">
        <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <span>
          These preferences are stored in this browser and control in-app alerts. Server-sent email
          (invoice reminders, dunning, trial notices) is not yet filtered by them.
        </span>
      </div>

      {/* Channels */}
      <SettingsSection
        title="Delivery Channels"
        description="Choose how you wish to receive operational alerts and reports."
      >
        <div className="space-y-1">
          <ToggleItem
            label="Email Alerts"
            description="Send notifications to your registered account email."
            checked={prefs.emailNotifications}
            onChange={(c) => update('emailNotifications', c)}
          />
          <ToggleItem
            label="In-App Action Center"
            description="Display badge counts and toast alerts inside the control center."
            checked={prefs.inAppNotifications}
            onChange={(c) => update('inAppNotifications', c)}
          />
        </div>
      </SettingsSection>

      {/* Billing Notifications */}
      <SettingsSection
        title="Billing Notifications"
        description="Alerts regarding payment attempts, invoice generation, and refund operations."
      >
        <div className="space-y-1">
          <ToggleItem
            label="Payment Received"
            description="Notification when a customer makes an online or manual payment successfully."
            checked={prefs.paymentReceived}
            onChange={(c) => update('paymentReceived', c)}
          />
          <ToggleItem
            label="Payment Failed"
            description="Alert when a Razorpay card or UPI transaction is declined or fails."
            checked={prefs.paymentFailed}
            onChange={(c) => update('paymentFailed', c)}
          />
          <ToggleItem
            label="Invoice Created"
            description="Receive an update when draft or recurring invoices are generated."
            checked={prefs.invoiceCreated}
            onChange={(c) => update('invoiceCreated', c)}
          />
          <ToggleItem
            label="Invoice Overdue"
            description="Alert when an unpaid invoice crosses its payment due date."
            checked={prefs.invoiceOverdue}
            onChange={(c) => update('invoiceOverdue', c)}
          />
          <ToggleItem
            label="Invoice Paid in Full"
            description="Confirmation when an outstanding invoice balance reaches zero."
            checked={prefs.invoicePaid}
            onChange={(c) => update('invoicePaid', c)}
          />
          <ToggleItem
            label="Refund Processed"
            description="Notification when gateway or manual refunds are recorded against an invoice."
            checked={prefs.refundProcessed}
            onChange={(c) => update('refundProcessed', c)}
          />
        </div>
      </SettingsSection>

      {/* Subscription Notifications */}
      <SettingsSection
        title="Subscription Notifications"
        description="Updates regarding subscription life cycles, renewals, and plan tier transitions."
      >
        <div className="space-y-1">
          <ToggleItem
            label="Subscription Created"
            description="Alert when a new subscription begins for a customer account."
            checked={prefs.subscriptionCreated}
            onChange={(c) => update('subscriptionCreated', c)}
          />
          <ToggleItem
            label="Subscription Upgraded"
            description="Notification when a subscriber changes to a higher pricing plan or adds units."
            checked={prefs.subscriptionUpgraded}
            onChange={(c) => update('subscriptionUpgraded', c)}
          />
          <ToggleItem
            label="Subscription Downgraded"
            description="Notification when a plan is switched to a lower tier."
            checked={prefs.subscriptionDowngraded}
            onChange={(c) => update('subscriptionDowngraded', c)}
          />
          <ToggleItem
            label="Subscription Cancelled"
            description="Immediate notification when a subscription is cancelled or scheduled to end."
            checked={prefs.subscriptionCancelled}
            onChange={(c) => update('subscriptionCancelled', c)}
          />
          <ToggleItem
            label="Trial Ending Soon"
            description="Reminder 3 days before a customer's product trial expires."
            checked={prefs.trialEnding}
            onChange={(c) => update('trialEnding', c)}
          />
          <ToggleItem
            label="Trial Expired"
            description="Alert when a trial finishes without an active payment conversion."
            checked={prefs.trialExpired}
            onChange={(c) => update('trialExpired', c)}
          />
        </div>
      </SettingsSection>

      {/* Customer Activity */}
      <SettingsSection
        title="Customer Activity"
        description="Notifications when customer accounts are created or client portal actions occur."
      >
        <div className="space-y-1">
          <ToggleItem
            label="New Customer Created"
            description="Notice when a new customer profile or organization contact is added."
            checked={prefs.newCustomer}
            onChange={(c) => update('newCustomer', c)}
          />
          <ToggleItem
            label="Customer Portal Activity"
            description="Alert when a client signs into their self-service portal or views quotes."
            checked={prefs.customerPortalActivity}
            onChange={(c) => update('customerPortalActivity', c)}
          />
          <ToggleItem
            label="Payment Method Changes"
            description="Notice when a customer adds or removes a card/UPI method in their portal."
            checked={prefs.paymentMethodChanges}
            onChange={(c) => update('paymentMethodChanges', c)}
          />
        </div>
      </SettingsSection>

      {/* System & Security */}
      <SettingsSection
        title="System & Security Alerts"
        description="Critical system health alerts, credential changes, and security events."
      >
        <div className="space-y-1">
          <ToggleItem
            label="System Alerts"
            description="Background scheduler notices, webhook retries, and automated job failures."
            checked={prefs.systemAlerts}
            onChange={(c) => update('systemAlerts', c)}
          />
          <ToggleItem
            label="Important Service Notifications"
            description="Planned platform maintenance, API rate updates, and service announcements."
            checked={prefs.serviceNotifications}
            onChange={(c) => update('serviceNotifications', c)}
          />
          <ToggleItem
            label="Security Alerts"
            description="Account logins from unrecognized IPs, password changes, and permission shifts."
            checked={prefs.securityAlerts}
            onChange={(c) => update('securityAlerts', c)}
          />
        </div>
      </SettingsSection>

      {/* Save Button */}
      <div className="flex items-center justify-end">
        <Button
          type="submit"
          variant="primary"
          isLoading={isSaving}
          leadingIcon={<Save className="w-4 h-4" />}
        >
          Save Notification Preferences
        </Button>
      </div>
    </form>
  );
}

export default NotificationsTab;
