import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Mail, Edit3, Eye, Send, CheckCircle2, XCircle, Webhook, MessageSquareOff } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { cn } from '../../utils/cn';
import { useAuth } from '../../hooks/useAuth';
import { toApiError } from '../../services/apiClient';
import { SettingsSection } from './settingsShared';
import {
  notificationService,
  type NotificationTemplate,
  type NotificationTemplateUpdate,
  type NotificationTemplatePreview,
  type NotificationPreferences,
  NOTIFICATION_CHANNEL_LABELS,
  SMS_NOT_AVAILABLE_MESSAGE,
  isChannelSupported,
  notificationQueryKeys,
} from '../../services/notificationService';

export type { NotificationPreferences };

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

interface ToggleItemProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

function ToggleItem({ label, description, checked, onChange, disabled = false }: ToggleItemProps) {
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
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer disabled:cursor-not-allowed disabled:opacity-60 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
          checked ? 'bg-primary-600' : 'bg-slate-200'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
            checked ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </button>
    </div>
  );
}

const AVAILABLE_PLACEHOLDERS = [
  '{{customer_name}}',
  '{{company_name}}',
  '{{invoice_number}}',
  '{{invoice_date}}',
  '{{due_date}}',
  '{{invoice_total}}',
  '{{amount_due}}',
  '{{payment_link}}',
  '{{quote_number}}',
  '{{quote_total}}',
  '{{payment_date}}',
  '{{payment_amount}}',
];

export function NotificationsTab() {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { user, organization } = useAuth();
  const prefsQueryKey = notificationQueryKeys.preferences(user?.id, organization?.id);
  const [prefs, setPrefs] = useState<NotificationPreferences>(DEFAULT_NOTIFICATIONS);

  // Preferences are stored server-side per user + organization, so they follow the user across
  // browsers and devices.
  const prefsQuery = useQuery({
    queryKey: prefsQueryKey,
    queryFn: () => notificationService.getPreferences(),
    enabled: Boolean(user?.id && organization?.id),
  });
  useEffect(() => {
    if (prefsQuery.data) setPrefs({ ...DEFAULT_NOTIFICATIONS, ...prefsQuery.data.preferences });
  }, [prefsQuery.data]);

  const savePrefsMutation = useMutation({
    mutationFn: (next: NotificationPreferences) => notificationService.updatePreferences(next),
    onSuccess: (data) => {
      queryClient.setQueryData(prefsQueryKey, data);
      showToast('success', 'Notification preferences saved', 'They apply wherever you sign in to this organization.');
    },
    onError: (err) => {
      showToast('error', 'Could not save preferences', toApiError(err).message);
    },
  });

  // Template state
  const [editingTemplate, setEditingTemplate] = useState<NotificationTemplate | null>(null);
  const [editForm, setEditForm] = useState<NotificationTemplateUpdate>({});
  const [previewingTemplate, setPreviewingTemplate] = useState<NotificationTemplate | null>(null);
  const [previewData, setPreviewData] = useState<NotificationTemplatePreview | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [testEmailRecipient, setTestEmailRecipient] = useState('');
  const [isSendingTest, setIsSendingTest] = useState(false);

  const { data: templates = [], isLoading: isLoadingTemplates } = useQuery({
    queryKey: ['notification-templates'],
    queryFn: () => notificationService.listTemplates(),
  });

  const updateTemplateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: NotificationTemplateUpdate }) =>
      notificationService.updateTemplate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-templates'] });
      showToast('success', 'Notification template updated successfully');
      setEditingTemplate(null);
    },
    onError: (err) => {
      showToast('error', 'Failed to update notification template', toApiError(err).message);
    },
  });

  const update = (key: keyof NotificationPreferences, value: boolean) => {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  };

  const handleSavePreferences = (e: React.FormEvent) => {
    e.preventDefault();
    savePrefsMutation.mutate(prefs);
  };
  const prefsDisabled = prefsQuery.isLoading || savePrefsMutation.isPending;

  const handleOpenEdit = (template: NotificationTemplate) => {
    setEditingTemplate(template);
    setEditForm({
      name: template.name,
      subject_template: template.subject_template || '',
      body_template: template.body_template,
      description: template.description || '',
      is_active: template.is_active,
    });
  };

  const handleSaveTemplate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTemplate) return;
    updateTemplateMutation.mutate({
      id: editingTemplate.id,
      data: editForm,
    });
  };

  const handleOpenPreview = async (template: NotificationTemplate) => {
    setPreviewingTemplate(template);
    setIsPreviewLoading(true);
    setTestEmailRecipient('');
    try {
      const rendered = await notificationService.previewTemplate(template.id);
      setPreviewData(rendered);
    } catch {
      showToast('error', 'Could not render template preview');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleSendTestEmail = async () => {
    if (!previewingTemplate || !testEmailRecipient) return;
    setIsSendingTest(true);
    try {
      const res = await notificationService.sendTestEmail(previewingTemplate.id, testEmailRecipient);
      if (res.success) {
        showToast('success', `Test email dispatched to ${testEmailRecipient}`);
      } else {
        showToast('warning', `SMTP is not configured. Email preview logged for ${testEmailRecipient}.`);
      }
    } catch {
      showToast('error', 'Failed to send test email. Check your SMTP settings.');
    } finally {
      setIsSendingTest(false);
    }
  };

  const insertPlaceholder = (tag: string) => {
    setEditForm((prev) => ({
      ...prev,
      body_template: (prev.body_template || '') + ' ' + tag,
    }));
  };

  return (
    <div className="space-y-8">
      {/* Email & Notification Templates */}
      <SettingsSection
        title="Email & Notification Templates"
        description="Standard customer-facing email templates dispatched upon invoice issuance, reminders, quotes, and payment receipts."
      >
        {isLoadingTemplates ? (
          <div className="py-6 text-center text-xs text-slate-400">Loading templates...</div>
        ) : (
          <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white overflow-hidden">
            {templates.map((tpl) => {
              const channelSupported = tpl.channel_supported ?? isChannelSupported(tpl.channel);
              const ChannelIcon = tpl.channel === 'webhook' ? Webhook : tpl.channel === 'sms' ? MessageSquareOff : Mail;
              return (
              <div key={tpl.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1 max-w-xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <ChannelIcon className={cn('w-4 h-4', channelSupported ? 'text-primary-600' : 'text-slate-400')} />
                    <span className="text-xs font-semibold text-slate-800">{tpl.name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      {tpl.code}
                    </span>
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      {NOTIFICATION_CHANNEL_LABELS[tpl.channel] ?? tpl.channel}
                    </span>
                    {!channelSupported ? (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] text-slate-600 font-medium bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full"
                        title={SMS_NOT_AVAILABLE_MESSAGE}
                      >
                        <XCircle className="w-3 h-3" /> Not available
                      </span>
                    ) : tpl.is_active ? (
                      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-medium bg-emerald-50 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="w-3 h-3" /> Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] text-amber-600 font-medium bg-amber-50 px-2 py-0.5 rounded-full">
                        <XCircle className="w-3 h-3" /> Disabled (Fallback)
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500">{tpl.description || 'Configured notification template.'}</p>
                  {!channelSupported && (
                    <p className="text-[11px] text-amber-700">{SMS_NOT_AVAILABLE_MESSAGE}. This template is never sent.</p>
                  )}
                  <p className="text-[11px] text-slate-400 truncate">
                    <span className="font-medium text-slate-600">Subject:</span> {tpl.subject_template || '(None)'}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    type="button"
                    disabled={!channelSupported && !tpl.is_active}
                    title={!channelSupported && !tpl.is_active ? SMS_NOT_AVAILABLE_MESSAGE : undefined}
                    onClick={() =>
                      updateTemplateMutation.mutate({
                        id: tpl.id,
                        data: { is_active: !tpl.is_active },
                      })
                    }
                    className={cn(
                      'text-xs px-2.5 py-1 rounded border font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
                      tpl.is_active
                        ? 'border-slate-200 text-slate-600 hover:bg-slate-50'
                        : 'border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100'
                    )}
                  >
                    {tpl.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleOpenPreview(tpl)}
                    leadingIcon={<Eye className="w-3.5 h-3.5" />}
                  >
                    Preview
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleOpenEdit(tpl)}
                    leadingIcon={<Edit3 className="w-3.5 h-3.5" />}
                  >
                    Edit
                  </Button>
                </div>
              </div>
              );
            })}
          </div>
        )}
      </SettingsSection>

      {/* Edit Template Modal */}
      <Modal
        isOpen={!!editingTemplate}
        onClose={() => setEditingTemplate(null)}
        title={`Edit Template: ${editingTemplate?.name}`}
        size="lg"
      >
        {editingTemplate && (
          <form onSubmit={handleSaveTemplate} className="space-y-4">
            <Input
              label="Template Name"
              value={editForm.name || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
              required
            />
            <Input
              label="Subject Template"
              value={editForm.subject_template || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, subject_template: e.target.value }))}
              placeholder="e.g. Invoice {{invoice_number}} from {{company_name}}"
              required
            />
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700">Body Template (HTML / Plain text)</label>
                <span className="text-[10px] text-slate-400">Click a variable to insert</span>
              </div>
              <div className="flex flex-wrap gap-1 mb-1.5">
                {AVAILABLE_PLACEHOLDERS.map((ph) => (
                  <button
                    key={ph}
                    type="button"
                    onClick={() => insertPlaceholder(ph)}
                    className="text-[10px] font-mono bg-primary-50 text-primary-700 px-1.5 py-0.5 rounded hover:bg-primary-100 border border-primary-200"
                  >
                    {ph}
                  </button>
                ))}
              </div>
              <textarea
                rows={8}
                value={editForm.body_template || ''}
                onChange={(e) => setEditForm((prev) => ({ ...prev, body_template: e.target.value }))}
                className="w-full font-mono text-xs rounded-md border border-slate-300 p-2.5 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                required
              />
            </div>
            <Input
              label="Description"
              value={editForm.description || ''}
              onChange={(e) => setEditForm((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Optional notes about when this template triggers"
            />
            <div className="flex items-center justify-between pt-2 border-t border-slate-100">
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  disabled={!isChannelSupported(editingTemplate.channel) && !editingTemplate.is_active}
                  checked={editForm.is_active ?? true}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, is_active: e.target.checked }))}
                  className="rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
                Active (dispatches customized email)
              </label>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" onClick={() => setEditingTemplate(null)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" isLoading={updateTemplateMutation.isPending}>
                  Save Template
                </Button>
              </div>
            </div>
          </form>
        )}
      </Modal>

      {/* Preview & Test Send Modal */}
      <Modal
        isOpen={!!previewingTemplate}
        onClose={() => setPreviewingTemplate(null)}
        title={`Preview & Test: ${previewingTemplate?.name}`}
        size="lg"
      >
        <div className="space-y-4">
          {isPreviewLoading ? (
            <div className="py-8 text-center text-xs text-slate-400">Rendering preview...</div>
          ) : previewData ? (
            <div className="space-y-3">
              <div className="bg-slate-50 border border-slate-200 rounded p-3">
                <p className="text-[11px] text-slate-400 font-medium">Subject</p>
                <p className="text-xs font-semibold text-slate-800 mt-0.5">{previewData.subject}</p>
              </div>

              <div>
                <p className="text-[11px] text-slate-400 font-medium mb-1">Rendered HTML</p>
                <iframe
                  title="Rendered HTML Email Preview"
                  sandbox=""
                  srcDoc={previewData.body_html}
                  className="w-full h-56 p-2 bg-white border border-slate-200 rounded text-xs text-slate-700"
                />
              </div>

              <div>
                <p className="text-[11px] text-slate-400 font-medium mb-1">Plain-Text Fallback</p>
                <pre className="p-3 bg-slate-900 text-slate-200 rounded text-[11px] font-mono whitespace-pre-wrap max-h-36 overflow-y-auto">
                  {previewData.body_text}
                </pre>
              </div>

              <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row items-center gap-2">
                <input
                  type="email"
                  placeholder="Enter test email (e.g. test@example.com)"
                  value={testEmailRecipient}
                  onChange={(e) => setTestEmailRecipient(e.target.value)}
                  className="flex-1 text-xs rounded-md border border-slate-300 px-3 py-2 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                />
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={handleSendTestEmail}
                  isLoading={isSendingTest}
                  disabled={!testEmailRecipient}
                  leadingIcon={<Send className="w-3.5 h-3.5" />}
                >
                  Send Test Email
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </Modal>

      {/* Existing Notification Preferences Form */}
      <form onSubmit={handleSavePreferences} className="space-y-6">
        {/* Billing Activity */}
        <SettingsSection
          title="Billing Notifications"
          description="In-app and internal notifications triggered when invoices are paid, overdue, or payments fail."
        >
          <div className="space-y-1">
            <ToggleItem
              label="Payment Received"
              description="Alert when an online or manual payment is successfully recorded."
              checked={prefs.paymentReceived}
              disabled={prefsDisabled}
              onChange={(c) => update('paymentReceived', c)}
            />
            <ToggleItem
              label="Payment Failed"
              description="Alert when a customer's online payment attempt is declined or fails."
              checked={prefs.paymentFailed}
              disabled={prefsDisabled}
              onChange={(c) => update('paymentFailed', c)}
            />
            <ToggleItem
              label="Invoice Created"
              description="Notify when a new draft or issued invoice is generated."
              checked={prefs.invoiceCreated}
              disabled={prefsDisabled}
              onChange={(c) => update('invoiceCreated', c)}
            />
            <ToggleItem
              label="Invoice Overdue"
              description="Notice when an issued invoice reaches its due date without payment."
              checked={prefs.invoiceOverdue}
              disabled={prefsDisabled}
              onChange={(c) => update('invoiceOverdue', c)}
            />
            <ToggleItem
              label="Invoice Fully Paid"
              description="Confirmation when an invoice balance reaches zero."
              checked={prefs.invoicePaid}
              disabled={prefsDisabled}
              onChange={(c) => update('invoicePaid', c)}
            />
            <ToggleItem
              label="Refund Processed"
              description="Alert when a payment refund or partial refund is processed."
              checked={prefs.refundProcessed}
              disabled={prefsDisabled}
              onChange={(c) => update('refundProcessed', c)}
            />
          </div>
        </SettingsSection>

        {/* Subscription Activity */}
        <SettingsSection
          title="Subscription Lifecycle"
          description="Alerts for customer subscription changes, renewals, and trial events."
        >
          <div className="space-y-1">
            <ToggleItem
              label="Subscription Created"
              description="Alert when a new recurring subscription is activated."
              checked={prefs.subscriptionCreated}
              disabled={prefsDisabled}
              onChange={(c) => update('subscriptionCreated', c)}
            />
            <ToggleItem
              label="Subscription Upgraded"
              description="Notice when a customer upgrades their tier or increases quantity."
              checked={prefs.subscriptionUpgraded}
              disabled={prefsDisabled}
              onChange={(c) => update('subscriptionUpgraded', c)}
            />
            <ToggleItem
              label="Subscription Downgraded"
              description="Notice when a customer downgrades to a lower plan tier."
              checked={prefs.subscriptionDowngraded}
              disabled={prefsDisabled}
              onChange={(c) => update('subscriptionDowngraded', c)}
            />
            <ToggleItem
              label="Subscription Cancelled"
              description="Immediate notification when a subscription is cancelled or scheduled to end."
              checked={prefs.subscriptionCancelled}
              disabled={prefsDisabled}
              onChange={(c) => update('subscriptionCancelled', c)}
            />
            <ToggleItem
              label="Trial Ending Soon"
              description="Reminder 3 days before a customer's product trial expires."
              checked={prefs.trialEnding}
              disabled={prefsDisabled}
              onChange={(c) => update('trialEnding', c)}
            />
            <ToggleItem
              label="Trial Expired"
              description="Alert when a trial finishes without an active payment conversion."
              checked={prefs.trialExpired}
              disabled={prefsDisabled}
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
              disabled={prefsDisabled}
              onChange={(c) => update('newCustomer', c)}
            />
            <ToggleItem
              label="Customer Portal Activity"
              description="Alert when a client signs into their self-service portal or views quotes."
              checked={prefs.customerPortalActivity}
              disabled={prefsDisabled}
              onChange={(c) => update('customerPortalActivity', c)}
            />
            <ToggleItem
              label="Payment Method Changes"
              description="Notice when a customer adds or removes a card/UPI method in their portal."
              checked={prefs.paymentMethodChanges}
              disabled={prefsDisabled}
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
              disabled={prefsDisabled}
              onChange={(c) => update('systemAlerts', c)}
            />
            <ToggleItem
              label="Important Service Notifications"
              description="Planned platform maintenance, API rate updates, and service announcements."
              checked={prefs.serviceNotifications}
              disabled={prefsDisabled}
              onChange={(c) => update('serviceNotifications', c)}
            />
            <ToggleItem
              label="Security Alerts"
              description="Account logins from unrecognized IPs, password changes, and permission shifts."
              checked={prefs.securityAlerts}
              disabled={prefsDisabled}
              onChange={(c) => update('securityAlerts', c)}
            />
          </div>
        </SettingsSection>

        {/* Save Button */}
        <div className="flex items-center justify-end gap-3">
          {prefsQuery.isError ? (
            <p className="text-xs text-rose-600">Could not load your saved preferences; showing defaults.</p>
          ) : (
            <p className="text-xs text-slate-500">Saved to your account for this organization.</p>
          )}
          <Button
            type="submit"
            variant="primary"
            isLoading={savePrefsMutation.isPending}
            disabled={prefsQuery.isLoading}
            leadingIcon={<Save className="w-4 h-4" />}
          >
            Save Notification Preferences
          </Button>
        </div>
      </form>
    </div>
  );
}

export default NotificationsTab;
