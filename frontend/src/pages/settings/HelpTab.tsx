import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  BookOpen,
  HelpCircle,
  MessageSquare,
  AlertTriangle,
  ChevronRight,
  Info,
  Layers,
  FileText,
  CreditCard,
  Repeat,
  Tag,
  Gauge,
  Scissors,
  Clock,
  Globe,
  Share2,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { useToast } from '../../components/common/Toast';
import { SettingsSection } from './settingsShared';

const QUICK_LINKS = [
  {
    title: 'Getting Started',
    desc: 'Overview of Rooman Billing setup, GSTIN config, and workspace tour.',
    path: '/dashboard',
    icon: Layers,
  },
  {
    title: 'Customers',
    desc: 'Manage client accounts, billing contacts, and GST/tax details.',
    path: '/customers',
    icon: BookOpen,
  },
  {
    title: 'Invoices',
    desc: 'Draft, send, record payments, and download Indian GST invoices.',
    path: '/invoices',
    icon: FileText,
  },
  {
    title: 'Payments',
    desc: 'Track Razorpay online payments, UPI, bank transfers, and receipts.',
    path: '/payments',
    icon: CreditCard,
  },
  {
    title: 'Subscriptions',
    desc: 'Recurring billing lifecycles, active periods, and renewals.',
    path: '/subscriptions',
    icon: Repeat,
  },
  {
    title: 'Plans & Pricing',
    desc: 'Configure monthly, quarterly, annual plans, and add-on pricing.',
    path: '/plans-pricing',
    icon: Tag,
  },
  {
    title: 'Usage Metering',
    desc: 'Track consumption-based events, aggregates, and meter overages.',
    path: '/usage',
    icon: Gauge,
  },
  {
    title: 'Proration',
    desc: 'Calculate mid-cycle plan upgrades, downgrades, and balance adjustments.',
    path: '/proration',
    icon: Scissors,
  },
  {
    title: 'Dunning & Recovery',
    desc: 'Automated retry schedules, overdue reminders, and grace periods.',
    path: '/dunning',
    icon: Clock,
  },
  {
    title: 'Customer Portal',
    desc: 'Self-service client billing access, invoice history, and payments.',
    path: '/customer-portal',
    icon: Globe,
  },
  {
    title: 'Hosted Payment Pages',
    desc: 'Shareable checkout links and hosted payment screens with Razorpay.',
    path: '/hosted-payment-pages',
    icon: Share2,
  },
];

const FAQS = [
  {
    q: 'How does GST calculation work on Indian invoices?',
    a: 'Invoices automatically apply CGST + SGST (for intra-state supplies) or IGST (for inter-state supplies) depending on the customer state code and your organization place of business.',
  },
  {
    q: 'How are recurring subscriptions billed automatically?',
    a: 'The background billing scheduler runs periodically to detect periods due for renewal, generates invoices with itemized line items, and fires configured dunning or notifications.',
  },
  {
    q: 'Where do I find Razorpay webhook settings?',
    a: 'Under Settings > Integrations, you will find your Razorpay credentials, Webhook URL, and supported payment methods for online checkout.',
  },
  {
    q: 'Can team members have different access levels?',
    a: 'Yes. Rooman Billing enforces role-based access control with Viewer, Finance, Admin, and Owner roles to restrict sensitive financial operations.',
  },
];

export function HelpTab() {
  const { showToast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [supportMessage, setSupportMessage] = useState('');
  const [reportIssue, setReportIssue] = useState('');

  const filteredLinks = QUICK_LINKS.filter(
    (item) =>
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.desc.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSendSupport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!supportMessage.trim()) return;
    showToast('success', 'Support message sent', 'Our support team will review your inquiry shortly.');
    setSupportMessage('');
    setIsSupportOpen(false);
  };

  const handleSendReport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportIssue.trim()) return;
    showToast('success', 'Problem report submitted', 'Thank you for helping us improve Rooman Billing.');
    setReportIssue('');
    setIsReportOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="bg-gradient-to-r from-brand-600 to-indigo-700 rounded-2xl p-6 text-white shadow-sm">
        <h2 className="text-lg font-bold">Help & Documentation Center</h2>
        <p className="text-xs text-blue-100 mt-1 max-w-xl">
          Search articles, guides, and module documentation to get the most out of Rooman Billing.
        </p>

        <div className="mt-4 max-w-xl relative">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search guides (e.g. invoices, subscriptions, razorpay)..."
            className="w-full pl-10 pr-4 py-2.5 bg-white text-slate-900 placeholder:text-slate-400 rounded-xl text-xs font-medium border-0 shadow-md focus:ring-2 focus:ring-brand-400 outline-none"
          />
        </div>
      </div>

      {/* Quick Links Section */}
      <SettingsSection
        title="Modules & Documentation"
        description="Jump straight into the relevant billing workspace or guide."
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredLinks.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.title}
                to={item.path}
                className="flex items-start gap-3 p-3 rounded-xl border border-slate-200/80 bg-white hover:border-brand-300 hover:bg-slate-50/70 transition-all group"
              >
                <div className="p-2 rounded-lg bg-slate-100 text-slate-600 group-hover:bg-brand-50 group-hover:text-brand-600 transition-colors shrink-0">
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-900 group-hover:text-brand-700 flex items-center justify-between">
                    <span>{item.title}</span>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
                  </p>
                  <p className="text-[11px] text-slate-500 line-clamp-2 mt-0.5 leading-snug">{item.desc}</p>
                </div>
              </Link>
            );
          })}
          {filteredLinks.length === 0 && (
            <div className="col-span-full py-8 text-center text-xs text-slate-400">
              No matching documentation found for "{searchQuery}".
            </div>
          )}
        </div>
      </SettingsSection>

      {/* FAQs */}
      <SettingsSection
        title="Frequently Asked Questions"
        description="Quick answers to common questions about billing operations."
      >
        <div className="space-y-2">
          {FAQS.map((faq, idx) => {
            const isOpen = expandedFaq === idx;
            return (
              <div
                key={faq.q}
                className="border border-slate-200/80 rounded-xl overflow-hidden transition-colors"
              >
                <button
                  type="button"
                  onClick={() => setExpandedFaq(isOpen ? null : idx)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left text-xs font-semibold text-slate-800 bg-white hover:bg-slate-50 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <HelpCircle className="w-3.5 h-3.5 text-brand-600 shrink-0" />
                    {faq.q}
                  </span>
                  <ChevronRight
                    className={`w-3.5 h-3.5 text-slate-400 transition-transform ${
                      isOpen ? 'rotate-90 text-brand-600' : ''
                    }`}
                  />
                </button>
                {isOpen && (
                  <div className="px-4 py-3 bg-slate-50/75 border-t border-slate-100 text-xs text-slate-600 leading-relaxed">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </SettingsSection>

      {/* Support & Version */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Contact Support */}
        <div className="p-4 rounded-xl border border-slate-200/80 bg-white flex flex-col justify-between space-y-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-slate-900 font-semibold text-xs">
              <MessageSquare className="w-4 h-4 text-brand-600" />
              <span>Contact Support</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-normal">
              Have questions regarding setup or payment reconciliation? Reach our support team directly.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setIsSupportOpen(true)}
            className="w-full justify-center"
          >
            Get in touch
          </Button>
        </div>

        {/* Report a Problem */}
        <div className="p-4 rounded-xl border border-slate-200/80 bg-white flex flex-col justify-between space-y-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-slate-900 font-semibold text-xs">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span>Report an Issue</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-normal">
              Encountered a bug or unexpected behavior in a module? Submit details to our engineering team.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setIsReportOpen(true)}
            className="w-full justify-center"
          >
            Report Problem
          </Button>
        </div>

        {/* Application Version */}
        <div className="p-4 rounded-xl border border-slate-200/80 bg-white flex flex-col justify-between space-y-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-slate-900 font-semibold text-xs">
              <Info className="w-4 h-4 text-slate-400" />
              <span>Application Version</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-normal">
              Rooman Enterprise Billing Platform
            </p>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between text-xs">
            <span className="text-slate-500 text-[11px]">Version</span>
            <span className="font-mono font-semibold text-slate-800">v0.1.0</span>
          </div>
        </div>
      </div>

      {/* Contact Support Modal */}
      <Modal
        isOpen={isSupportOpen}
        onClose={() => setIsSupportOpen(false)}
        title="Contact Rooman Support"
        description="Send a message to our support staff."
        size="md"
      >
        <form onSubmit={handleSendSupport} className="space-y-4">
          <div className="space-y-1">
            <label className="block text-xs font-medium text-slate-700">How can we help you?</label>
            <textarea
              rows={4}
              value={supportMessage}
              onChange={(e) => setSupportMessage(e.target.value)}
              required
              placeholder="Describe your inquiry or question in detail..."
              className="w-full p-2.5 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:ring-1 focus:ring-brand-500 focus:border-brand-500 outline-none"
            />
          </div>

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIsSupportOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Send Message
            </Button>
          </div>
        </form>
      </Modal>

      {/* Report Problem Modal */}
      <Modal
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        title="Report a Problem"
        description="Submit unexpected behavior or bug report."
        size="md"
      >
        <form onSubmit={handleSendReport} className="space-y-4">
          <div className="space-y-1">
            <label className="block text-xs font-medium text-slate-700">Problem Description</label>
            <textarea
              rows={4}
              value={reportIssue}
              onChange={(e) => setReportIssue(e.target.value)}
              required
              placeholder="What happened? Include steps to reproduce if applicable..."
              className="w-full p-2.5 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:ring-1 focus:ring-brand-500 focus:border-brand-500 outline-none"
            />
          </div>

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
            <Button type="button" variant="outline" onClick={() => setIsReportOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Submit Report
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default HelpTab;
