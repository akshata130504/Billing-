import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  CloudCog,
  CreditCard,
  Database,
  Mail,
  Send,
  Users,
  Webhook,
} from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import {
  integrationsService,
  AllIntegrationsStatus,
  RazorpayStatus,
  SMTPStatus,
  WebhookStatus,
} from '../../services/integrationsService';
import { toApiError } from '../../services/apiClient';
import { cn } from '../../utils/cn';
import { usePageSpec } from '../../appUi/usePageSpec';

function formatTestedAt(isoString?: string | null): string {
  if (!isoString) return 'Not tested recently';
  try {
    const d = new Date(isoString);
    return d.toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function StatusBadge({ connected }: { connected: boolean }) {
  return (
    <Badge variant={connected ? 'success' : 'neutral'} size="sm" dot>
      {connected ? 'Connected' : 'Not connected'}
    </Badge>
  );
}

function CategoryHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{children}</h3>;
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------

interface RazorpayModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStatus: RazorpayStatus;
  onSaved: () => void;
}

function RazorpayModal({ isOpen, onClose, currentStatus, onSaved }: RazorpayModalProps) {
  const [keyId, setKeyId] = useState('');
  const [keySecret, setKeySecret] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [mode, setMode] = useState<'test' | 'live'>(currentStatus.mode || 'test');

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleTest = async () => {
    if (!keyId.trim() || !keySecret.trim()) {
      setFeedback({ type: 'error', text: 'Please enter both Key ID and Key Secret to test.' });
      return;
    }
    setTesting(true);
    setFeedback(null);
    try {
      const res = await integrationsService.testRazorpay({
        key_id: keyId.trim(),
        key_secret: keySecret.trim(),
      });
      setFeedback({ type: 'success', text: res.message || 'Credentials verified successfully with Razorpay API.' });
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyId.trim() || !keySecret.trim()) {
      setFeedback({ type: 'error', text: 'Please provide both Key ID and Key Secret.' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      await integrationsService.configureRazorpay({
        key_id: keyId.trim(),
        key_secret: keySecret.trim(),
        webhook_secret: webhookSecret.trim() || undefined,
        mode,
      });
      onSaved();
      onClose();
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Configure Razorpay"
      description="Connect your Razorpay account to process online payments on invoice checkout pages."
      size="md"
    >
      <form onSubmit={handleSave} className="space-y-4">
        {feedback && (
          <div
            className={cn(
              'p-3 rounded-lg text-xs flex items-start gap-2',
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-rose-50 text-rose-800 border border-rose-200'
            )}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div>{feedback.text}</div>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Environment Mode</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as 'test' | 'live')}
            className="w-full text-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-900 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          >
            <option value="test">Test Mode (for development and staging)</option>
            <option value="live">Live Mode (production payments)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Key ID <span className="text-rose-500">*</span>
          </label>
          <input
            type="text"
            value={keyId}
            onChange={(e) => setKeyId(e.target.value)}
            placeholder={currentStatus.masked_key_id ? `Current: ${currentStatus.masked_key_id}` : 'rzp_test_...'}
            className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            required
          />
          <p className="text-[11px] text-slate-400 mt-1">Found in your Razorpay Dashboard &rarr; Settings &rarr; API Keys.</p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Key Secret <span className="text-rose-500">*</span>
          </label>
          <input
            type="password"
            value={keySecret}
            onChange={(e) => setKeySecret(e.target.value)}
            placeholder={currentStatus.is_connected ? '•••••••••••••••• (Enter new to update)' : 'Enter Razorpay Key Secret'}
            className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            required
          />
          <p className="text-[11px] text-slate-400 mt-1">Encrypted at rest with AES-128 and never transmitted back to the browser.</p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Webhook Secret (Optional)</label>
          <input
            type="password"
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder={currentStatus.has_webhook_secret ? '•••••••• (Configured)' : 'Enter Webhook Secret for signature validation'}
            className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          <p className="text-[11px] text-slate-400 mt-1">Used to verify incoming notifications on <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">/api/v1/webhooks</code>.</p>
        </div>

        <div className="pt-2 flex items-center justify-between border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleTest}
            disabled={testing || saving || !keyId || !keySecret}
            isLoading={testing}
          >
            Test Connection
          </Button>

          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm" isLoading={saving}>
              Save & Connect
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

interface SMTPModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStatus: SMTPStatus;
  onSaved: () => void;
}

function SMTPModal({ isOpen, onClose, currentStatus, onSaved }: SMTPModalProps) {
  const [host, setHost] = useState(currentStatus.host || '');
  const [port, setPort] = useState(currentStatus.port || 587);
  const [username, setUsername] = useState(currentStatus.username || '');
  const [password, setPassword] = useState('');
  const [useTls, setUseTls] = useState(currentStatus.use_tls ?? true);
  const [useSsl, setUseSsl] = useState(currentStatus.use_ssl ?? false);
  const [fromEmail, setFromEmail] = useState(currentStatus.from_email || '');
  const [fromName, setFromName] = useState(currentStatus.from_name || 'Rooman Billing');

  const [testEmailRecipient, setTestEmailRecipient] = useState('');
  const [testing, setTesting] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleTest = async () => {
    if (!host.trim()) {
      setFeedback({ type: 'error', text: 'Please enter the SMTP Host.' });
      return;
    }
    setTesting(true);
    setFeedback(null);
    try {
      const res = await integrationsService.testSMTP({
        host: host.trim(),
        port: Number(port),
        username: username.trim() || undefined,
        password: password.trim() || undefined,
        use_tls: useTls,
        use_ssl: useSsl,
      });
      setFeedback({ type: 'success', text: res.message || 'SMTP handshake and authentication verified successfully.' });
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setTesting(false);
    }
  };

  const handleSendTestEmail = async () => {
    if (!testEmailRecipient.trim() || !testEmailRecipient.includes('@')) {
      setFeedback({ type: 'error', text: 'Please enter a valid recipient email address.' });
      return;
    }
    setSendingEmail(true);
    setFeedback(null);
    try {
      const res = await integrationsService.sendTestEmail({
        recipient_email: testEmailRecipient.trim(),
        host: host.trim() || undefined,
        port: Number(port),
        username: username.trim() || undefined,
        password: password.trim() || undefined,
        use_tls: useTls,
        use_ssl: useSsl,
        from_email: fromEmail.trim() || undefined,
        from_name: fromName.trim() || undefined,
      });
      setFeedback({ type: 'success', text: res.message });
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setSendingEmail(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!host.trim() || !fromEmail.trim()) {
      setFeedback({ type: 'error', text: 'Host and From Email are required.' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      await integrationsService.configureSMTP({
        host: host.trim(),
        port: Number(port),
        username: username.trim() || undefined,
        password: password.trim() || undefined,
        use_tls: useTls,
        use_ssl: useSsl,
        from_email: fromEmail.trim(),
        from_name: fromName.trim(),
      });
      onSaved();
      onClose();
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Configure Outbound Email (SMTP)"
      description="Connect your mail server to deliver invoices, payment receipts, quote links, and invitations."
      size="md"
    >
      <form onSubmit={handleSave} className="space-y-3.5">
        {feedback && (
          <div
            className={cn(
              'p-3 rounded-lg text-xs flex items-start gap-2',
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-rose-50 text-rose-800 border border-rose-200'
            )}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div>{feedback.text}</div>
          </div>
        )}

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              SMTP Host <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="smtp.mailgun.org or smtp.gmail.com"
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Port</label>
            <input
              type="number"
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 focus:ring-2 focus:ring-brand-500 focus:outline-none"
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="postmaster@domain.com"
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={currentStatus.has_password ? '•••••••• (Enter new to update)' : 'App password or key'}
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="flex items-center gap-6 py-1">
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={useTls}
              onChange={(e) => {
                setUseTls(e.target.checked);
                if (e.target.checked) setUseSsl(false);
              }}
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            STARTTLS (Port 587 default)
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={useSsl}
              onChange={(e) => {
                setUseSsl(e.target.checked);
                if (e.target.checked) setUseTls(false);
              }}
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            SSL / Direct TLS (Port 465 default)
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3 pt-1 border-t border-slate-100">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Sender Name</label>
            <input
              type="text"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder="Rooman Billing"
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Sender Email <span className="text-rose-500">*</span>
            </label>
            <input
              type="email"
              value={fromEmail}
              onChange={(e) => setFromEmail(e.target.value)}
              placeholder="billing@example.com"
              className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
              required
            />
          </div>
        </div>

        {/* Live Test Email Section */}
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
          <span className="text-xs font-semibold text-slate-800">Send Test Email</span>
          <div className="flex gap-2">
            <input
              type="email"
              value={testEmailRecipient}
              onChange={(e) => setTestEmailRecipient(e.target.value)}
              placeholder="recipient@example.com"
              className="flex-1 text-xs rounded-lg border border-slate-200 px-3 py-1.5 bg-white text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleSendTestEmail}
              disabled={sendingEmail || !testEmailRecipient}
              isLoading={sendingEmail}
              leadingIcon={<Send className="w-3.5 h-3.5" />}
            >
              Send Test
            </Button>
          </div>
        </div>

        <div className="pt-2 flex items-center justify-between border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleTest}
            disabled={testing || saving || !host}
            isLoading={testing}
          >
            Test Connection
          </Button>

          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm" isLoading={saving}>
              Save & Connect
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

interface WebhookModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStatus: WebhookStatus;
  /** Receives the save response (may carry a one-time `generated_signing_secret`). */
  onSaved: (status: WebhookStatus) => void;
}

const AVAILABLE_WEBHOOK_EVENTS = [
  { id: 'invoice.issued', label: 'Invoice Issued' },
  { id: 'invoice.paid', label: 'Invoice Paid' },
  { id: 'payment.captured', label: 'Payment Captured' },
  { id: 'subscription.created', label: 'Subscription Created' },
  { id: 'subscription.cancelled', label: 'Subscription Cancelled' },
  { id: 'refund.processed', label: 'Refund Processed' },
];

function WebhookModal({ isOpen, onClose, currentStatus, onSaved }: WebhookModalProps) {
  const [url, setUrl] = useState(currentStatus.url || '');
  const [signingSecret, setSigningSecret] = useState('');
  const [events, setEvents] = useState<string[]>(
    currentStatus.events && currentStatus.events.length > 0
      ? currentStatus.events
      : ['invoice.paid', 'payment.captured']
  );
  const [isEnabled, setIsEnabled] = useState(currentStatus.is_connected);

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const toggleEvent = (eventId: string) => {
    setEvents((prev) =>
      prev.includes(eventId) ? prev.filter((e) => e !== eventId) : [...prev, eventId]
    );
  };

  const handleTest = async () => {
    if (!url.trim() || !url.startsWith('http')) {
      setFeedback({ type: 'error', text: 'Please enter a valid HTTP/HTTPS Webhook URL to test.' });
      return;
    }
    setTesting(true);
    setFeedback(null);
    try {
      const res = await integrationsService.testWebhook({
        url: url.trim(),
        signing_secret: signingSecret.trim() || undefined,
        event_type: 'test.ping',
      });
      setFeedback({ type: 'success', text: res.message || 'Webhook ping delivered successfully.' });
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      setFeedback({ type: 'error', text: 'Endpoint URL is required.' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      const saved = await integrationsService.configureWebhook({
        url: url.trim(),
        signing_secret: signingSecret.trim() || undefined,
        events,
        is_enabled: isEnabled,
      });
      onSaved(saved);
      onClose();
    } catch (err: any) {
      setFeedback({ type: 'error', text: toApiError(err).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Configure Outbound Webhooks"
      description="Send real-time HTTP POST notifications signed with HMAC-SHA256 whenever billing events happen."
      size="md"
    >
      <form onSubmit={handleSave} className="space-y-4">
        {feedback && (
          <div
            className={cn(
              'p-3 rounded-lg text-xs flex items-start gap-2',
              feedback.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-rose-50 text-rose-800 border border-rose-200'
            )}
          >
            {feedback.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div>{feedback.text}</div>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Endpoint URL <span className="text-rose-500">*</span>
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.yourcompany.com/billing-webhook"
            className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            required
          />
          <p className="text-[11px] text-slate-400 mt-1">Must accept POST requests with JSON body.</p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Signing Secret (Optional)</label>
          <input
            type="password"
            value={signingSecret}
            onChange={(e) => setSigningSecret(e.target.value)}
            placeholder={currentStatus.has_signing_secret ? '•••••••• (Configured)' : 'whsec_...'}
            className="w-full text-xs rounded-lg border border-slate-200 px-3 py-2 font-mono text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          <p className="text-[11px] text-slate-400 mt-1">Sent in header <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">X-Rooman-Signature: sha256=...</code></p>
        </div>

        <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
          <div>
            <span className="text-xs font-semibold text-slate-800">Delivery Status</span>
            <p className="text-[11px] text-slate-500">Enable or pause outbound event dispatches to this endpoint.</p>
          </div>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isEnabled}
              onChange={(e) => setIsEnabled(e.target.checked)}
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            {isEnabled ? 'Active' : 'Disabled'}
          </label>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-2">Subscribed Events</label>
          <div className="grid grid-cols-2 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-100">
            {AVAILABLE_WEBHOOK_EVENTS.map((ev) => (
              <label key={ev.id} className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={events.includes(ev.id)}
                  onChange={() => toggleEvent(ev.id)}
                  className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <span>{ev.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="pt-2 flex items-center justify-between border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleTest}
            disabled={testing || saving || !url}
            isLoading={testing}
          >
            Test Webhook
          </Button>

          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm" isLoading={saving}>
              Save & Connect
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Card Components
// ---------------------------------------------------------------------------

function ActiveIntegrationCard({
  icon,
  iconClass,
  name,
  description,
  connected,
  detail,
  lastTestedAt,
  onConfigure,
  onDisconnect,
  isDisconnecting,
}: {
  icon: React.ReactNode;
  iconClass: string;
  name: string;
  description: string;
  connected: boolean;
  detail: React.ReactNode;
  lastTestedAt?: string | null;
  onConfigure: () => void;
  onDisconnect: () => void;
  isDisconnecting?: boolean;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card p-4 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
      <div className="flex items-start gap-3 min-w-0">
        <div className={cn('p-2.5 rounded-xl border shrink-0', iconClass)}>{icon}</div>
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm text-slate-900">{name}</span>
            <StatusBadge connected={connected} />
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">{description}</p>
          <div className="text-xs text-slate-600 pt-0.5">{detail}</div>
          {connected && lastTestedAt && (
            <div className="text-[11px] text-slate-400">
              Last verified: <span className="text-slate-600 font-medium">{formatTestedAt(lastTestedAt)}</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 self-end sm:self-start">
        {connected ? (
          <>
            <Button variant="outline" size="sm" onClick={onConfigure}>
              Manage
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={onDisconnect}
              isLoading={isDisconnecting}
              disabled={isDisconnecting}
            >
              Disconnect
            </Button>
          </>
        ) : (
          <Button variant="primary" size="sm" onClick={onConfigure}>
            Configure
          </Button>
        )}
      </div>
    </div>
  );
}

function ComingSoonCard({
  icon,
  name,
  description,
}: {
  icon: React.ReactNode;
  name: string;
  description: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-card p-4 flex items-start justify-between gap-3 opacity-90">
      <div className="flex items-start gap-3 min-w-0">
        <div className="p-2.5 rounded-xl border bg-slate-50 text-slate-400 border-slate-200 shrink-0">{icon}</div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm text-slate-900">{name}</span>
            <Badge variant="neutral" size="sm">
              Coming soon
            </Badge>
          </div>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
          <p className="text-[11px] text-slate-400 mt-1">Provider connector not available yet.</p>
        </div>
      </div>
      <div className="shrink-0" title="Provider connector not implemented yet">
        <Button variant="outline" size="sm" disabled>
          Configure
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main IntegrationsTab Component
// ---------------------------------------------------------------------------

export function IntegrationsTab() {
  const queryClient = useQueryClient();
  const ui = usePageSpec('integrations');

  const { data, isPending, isError, error, refetch } = useQuery<AllIntegrationsStatus>({
    queryKey: ['settings', 'integrations'],
    queryFn: integrationsService.getAll,
  });

  const { showToast } = useToast();
  const [activeModal, setActiveModal] = useState<'razorpay' | 'smtp' | 'webhook' | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState<'razorpay' | 'smtp' | 'webhook' | null>(null);
  // Server-generated webhook signing secret: returned once in the save response.
  const [generatedSecret, setGeneratedSecret] = useState<string | null>(null);

  // Disconnect mutations
  const disconnectRazorpayMutation = useMutation({
    mutationFn: integrationsService.disconnectRazorpay,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings', 'integrations'] }),
  });

  const disconnectSMTPMutation = useMutation({
    mutationFn: integrationsService.disconnectSMTP,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings', 'integrations'] }),
  });

  const disconnectWebhookMutation = useMutation({
    mutationFn: integrationsService.disconnectWebhook,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings', 'integrations'] }),
  });

  if (isPending) return <LoadingState message="Checking integration connections..." />;
  if (isError) {
    return <ErrorState message={toApiError(error).message} onRetry={() => void refetch()} />;
  }

  const { razorpay, smtp, webhook } = data;

  const DISCONNECT = {
    razorpay: {
      title: 'Disconnect Razorpay',
      description: 'Are you sure you want to disconnect Razorpay? Online invoice checkout will be disabled.',
      mutation: disconnectRazorpayMutation,
    },
    smtp: {
      title: 'Disconnect SMTP',
      description: 'Are you sure you want to disconnect SMTP? Outbound emails will be disabled.',
      mutation: disconnectSMTPMutation,
    },
    webhook: {
      title: 'Disconnect Webhooks',
      description: 'Are you sure you want to disconnect outbound webhooks?',
      mutation: disconnectWebhookMutation,
    },
  } as const;

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-200 pb-4" {...ui.edit('header')}>
        <h2 className="text-base font-semibold text-slate-900">
          {ui.text('header', 'title')}
        </h2>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          {ui.text('header', 'subtitle')}
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600 leading-relaxed">
        Configure live external integrations for payments, email delivery, and event webhooks. Sensitive credentials
        are encrypted at rest and never exposed to the client.
      </div>

      <div className="space-y-6" {...ui.edit('cards')}>
        {ui.render('cards', {
          razorpay: (item, edit) => (
            <div key={item.key} className="space-y-3" {...edit}>
              <CategoryHeading>Payments</CategoryHeading>
              <ActiveIntegrationCard
                icon={<CreditCard className="w-5 h-5" />}
                iconClass="bg-blue-50 text-brand-600 border-blue-100"
                name={item.label}
                description={item.caption || 'Accept online credit card, debit card, UPI, and netbanking payments directly on invoice checkout pages.'}
                connected={razorpay.is_connected}
                lastTestedAt={razorpay.last_tested_at}
                detail={
                  razorpay.is_connected ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span>
                        Key ID:{' '}
                        <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-slate-800">
                          {razorpay.masked_key_id}
                        </code>
                      </span>
                      <span className="text-slate-400">&bull;</span>
                      <span className="capitalize">{razorpay.mode} mode</span>
                      {razorpay.has_webhook_secret && (
                        <>
                          <span className="text-slate-400">&bull;</span>
                          <span>Webhook verified</span>
                        </>
                      )}
                    </div>
                  ) : (
                    'The "Pay online" option is hidden on invoice payment pages until configured.'
                  )
                }
                onConfigure={() => setActiveModal('razorpay')}
                onDisconnect={() => setConfirmDisconnect('razorpay')}
                isDisconnecting={disconnectRazorpayMutation.isPending}
              />
            </div>
          ),
          smtp: (item, edit) => (
            <div key={item.key} className="space-y-3" {...edit}>
              <CategoryHeading>Email</CategoryHeading>
              <ActiveIntegrationCard
                icon={<Mail className="w-5 h-5" />}
                iconClass="bg-amber-50 text-amber-600 border-amber-100"
                name={item.label}
                description={item.caption || 'Sends invoices, payment receipts, quote approval links, team invitations, and password resets.'}
                connected={smtp.is_connected}
                lastTestedAt={smtp.last_tested_at}
                detail={
                  smtp.is_connected ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span>
                        Host:{' '}
                        <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-slate-800">
                          {smtp.host}:{smtp.port}
                        </code>
                      </span>
                      <span className="text-slate-400">&bull;</span>
                      <span>From: {smtp.from_email}</span>
                      <span className="text-slate-400">&bull;</span>
                      <span>{smtp.use_ssl ? 'SSL' : smtp.use_tls ? 'STARTTLS' : 'Plain'}</span>
                    </div>
                  ) : (
                    'Emails are disabled. Team invitation and password-reset links will be surfaced in the UI instead.'
                  )
                }
                onConfigure={() => setActiveModal('smtp')}
                onDisconnect={() => setConfirmDisconnect('smtp')}
                isDisconnecting={disconnectSMTPMutation.isPending}
              />
            </div>
          ),
          webhook: (item, edit) => (
            <div key={item.key} className="space-y-3" {...edit}>
              <CategoryHeading>Webhooks / API</CategoryHeading>
              <ActiveIntegrationCard
                icon={<Webhook className="w-5 h-5" />}
                iconClass="bg-purple-50 text-purple-600 border-purple-100"
                name={item.label}
                description={item.caption || 'Notify external billing, CRM, or accounting systems via signed HTTP POST requests on billing events.'}
                connected={webhook.is_connected}
                lastTestedAt={webhook.last_tested_at}
                detail={
                  webhook.is_connected ? (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="truncate max-w-sm">
                          URL:{' '}
                          <code className="font-mono bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-slate-800">
                            {webhook.url}
                          </code>
                        </span>
                        {webhook.has_signing_secret && (
                          <>
                            <span className="text-slate-400">&bull;</span>
                            <span>HMAC signed</span>
                          </>
                        )}
                      </div>
                      {webhook.events && webhook.events.length > 0 && (
                        <div className="text-[11px] text-slate-500">
                          Subscribed: {webhook.events.join(', ')}
                        </div>
                      )}
                    </div>
                  ) : (
                    'No outbound webhook endpoint connected.'
                  )
                }
                onConfigure={() => setActiveModal('webhook')}
                onDisconnect={() => setConfirmDisconnect('webhook')}
                isDisconnecting={disconnectWebhookMutation.isPending}
              />
            </div>
          ),
        })}
      </div>

      {/* Accounting */}
      <div className="space-y-3">
        <CategoryHeading>Accounting</CategoryHeading>
        <ComingSoonCard
          icon={<BookOpen className="w-5 h-5" />}
          name="Accounting Sync"
          description="Sync invoices, payments, and credit notes with an external accounting ledger."
        />
      </div>

      {/* CRM */}
      <div className="space-y-3">
        <CategoryHeading>CRM</CategoryHeading>
        <ComingSoonCard
          icon={<Users className="w-5 h-5" />}
          name="CRM Sync"
          description="Keep customer and deal records synchronized with an external CRM."
        />
      </div>

      {/* Cloud Storage */}
      <div className="space-y-3">
        <CategoryHeading>Storage</CategoryHeading>
        <ComingSoonCard
          icon={<Database className="w-5 h-5" />}
          name="Cloud Storage"
          description="Back up generated invoice PDFs, receipts, and reports to external object storage."
        />
      </div>

      {/* Footer Info */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-500 flex items-start gap-2">
        <CloudCog className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" />
        Accounting, CRM, and cloud storage connectors are scheduled for future platform releases and remain disconnected.
      </div>

      {/* Modals */}
      {activeModal === 'razorpay' && (
        <RazorpayModal
          isOpen={true}
          onClose={() => setActiveModal(null)}
          currentStatus={razorpay}
          onSaved={() => void refetch()}
        />
      )}

      {activeModal === 'smtp' && (
        <SMTPModal
          isOpen={true}
          onClose={() => setActiveModal(null)}
          currentStatus={smtp}
          onSaved={() => void refetch()}
        />
      )}

      {activeModal === 'webhook' && (
        <WebhookModal
          isOpen={true}
          onClose={() => setActiveModal(null)}
          currentStatus={webhook}
          onSaved={(saved) => {
            if (saved.generated_signing_secret) setGeneratedSecret(saved.generated_signing_secret);
            void refetch();
          }}
        />
      )}

      <ConfirmDialog
        isOpen={confirmDisconnect !== null}
        onClose={() => setConfirmDisconnect(null)}
        onConfirm={() => {
          const target = confirmDisconnect;
          setConfirmDisconnect(null);
          if (target) DISCONNECT[target].mutation.mutate();
        }}
        title={confirmDisconnect ? DISCONNECT[confirmDisconnect].title : ''}
        description={confirmDisconnect ? DISCONNECT[confirmDisconnect].description : undefined}
        confirmLabel="Disconnect"
        variant="danger"
      />

      <Modal
        isOpen={generatedSecret !== null}
        onClose={() => setGeneratedSecret(null)}
        title="Webhook signing secret"
        description="Store this now - it won't be shown again. Receivers use it to verify the HMAC-SHA256 signature on each delivery."
        size="md"
        footer={
          <Button type="button" onClick={() => setGeneratedSecret(null)}>
            I have saved it
          </Button>
        }
      >
        <div className="flex items-center gap-2">
          <code className="flex-1 break-all rounded bg-slate-50 border border-slate-200 px-2 py-1 text-xs text-slate-800">
            {generatedSecret}
          </code>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              if (generatedSecret) void navigator.clipboard?.writeText(generatedSecret);
              showToast('success', 'Copied', 'Signing secret copied to clipboard.');
            }}
          >
            Copy
          </Button>
        </div>
      </Modal>
    </div>
  );
}

export default IntegrationsTab;
