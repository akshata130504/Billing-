import { useState, useEffect } from 'react';
import { Sun, Moon, Laptop, Save } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { cn } from '../../utils/cn';
import { SettingsSection } from './settingsShared';

const PREFERENCES_STORAGE_KEY = 'rooman_account_preferences';

export interface AccountPreferences {
  theme: 'light' | 'dark' | 'system';
  timezone: string;
  dateFormat: string;
  numberFormat: string;
  currencyDisplay: 'symbol' | 'code';
  defaultLandingPage: string;
  tableDensity: 'comfortable' | 'compact';
  confirmBeforeDelete: boolean;
  confirmBeforeSendInvoice: boolean;
}

const DEFAULT_PREFERENCES: AccountPreferences = {
  theme: 'light',
  timezone: 'Asia/Kolkata',
  dateFormat: 'DD/MM/YYYY',
  numberFormat: 'en-IN',
  currencyDisplay: 'symbol',
  defaultLandingPage: '/dashboard',
  tableDensity: 'comfortable',
  confirmBeforeDelete: true,
  confirmBeforeSendInvoice: true,
};

export function applyTheme(theme: 'light' | 'dark' | 'system') {
  if (typeof document === 'undefined') return;
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);

  if (isDark) {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

function loadPreferences(): AccountPreferences {
  try {
    const raw = localStorage.getItem(PREFERENCES_STORAGE_KEY);
    return raw ? { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) } : DEFAULT_PREFERENCES;
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function savePreferences(prefs: AccountPreferences) {
  try {
    localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Storage unavailable
  }
}

export function PreferencesTab() {
  const { showToast } = useToast();
  const [prefs, setPrefs] = useState<AccountPreferences>(loadPreferences);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    applyTheme(prefs.theme);
  }, []);

  useEffect(() => {
    if (prefs.theme !== 'system' || typeof window === 'undefined') return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const listener = () => applyTheme('system');
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [prefs.theme]);

  const handleThemeSelect = (theme: 'light' | 'dark' | 'system') => {
    setPrefs((p) => ({ ...p, theme }));
    applyTheme(theme);
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      savePreferences(prefs);
      applyTheme(prefs.theme);
      showToast('success', 'Preferences saved', 'Your account preferences have been successfully updated.');
    } catch {
      showToast('error', 'Save failed', 'Could not save your preferences.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Appearance Section */}
      <SettingsSection
        title="Appearance"
        description="Customize how the Rooman Billing interface looks on your screen."
      >
        <div className="space-y-3">
          <label className="block text-xs font-semibold text-slate-700">Theme mode</label>
          <div className="grid grid-cols-3 gap-3 max-w-lg">
            <button
              type="button"
              onClick={() => handleThemeSelect('light')}
              className={cn(
                'flex flex-col items-center justify-center p-3.5 rounded-xl border text-center transition-all cursor-pointer',
                prefs.theme === 'light'
                  ? 'border-brand-600 bg-brand-50/50 text-brand-700 ring-2 ring-brand-600/20'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
              )}
            >
              <Sun className={cn('w-5 h-5 mb-1.5', prefs.theme === 'light' ? 'text-brand-600' : 'text-slate-400')} />
              <span className="text-xs font-semibold">Light</span>
              <span className="text-[10px] text-slate-400">Default clean theme</span>
            </button>

            <button
              type="button"
              onClick={() => handleThemeSelect('dark')}
              className={cn(
                'flex flex-col items-center justify-center p-3.5 rounded-xl border text-center transition-all cursor-pointer',
                prefs.theme === 'dark'
                  ? 'border-brand-600 bg-brand-50/50 text-brand-700 ring-2 ring-brand-600/20'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
              )}
            >
              <Moon className={cn('w-5 h-5 mb-1.5', prefs.theme === 'dark' ? 'text-brand-600' : 'text-slate-400')} />
              <span className="text-xs font-semibold">Dark</span>
              <span className="text-[10px] text-slate-400">Reduced eye strain</span>
            </button>

            <button
              type="button"
              onClick={() => handleThemeSelect('system')}
              className={cn(
                'flex flex-col items-center justify-center p-3.5 rounded-xl border text-center transition-all cursor-pointer',
                prefs.theme === 'system'
                  ? 'border-brand-600 bg-brand-50/50 text-brand-700 ring-2 ring-brand-600/20'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
              )}
            >
              <Laptop className={cn('w-5 h-5 mb-1.5', prefs.theme === 'system' ? 'text-brand-600' : 'text-slate-400')} />
              <span className="text-xs font-semibold">System</span>
              <span className="text-[10px] text-slate-400">Sync with OS</span>
            </button>
          </div>
        </div>
      </SettingsSection>

      {/* Regional & Localization */}
      <SettingsSection
        title="Regional & Localization"
        description="Configure date, time, and numeric formatting according to your operating region."
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
          <Select
            label="Timezone"
            value={prefs.timezone}
            onChange={(e) => setPrefs((p) => ({ ...p, timezone: e.target.value }))}
            options={[
              { value: 'Asia/Kolkata', label: 'Asia/Kolkata (IST, UTC+05:30)' },
              { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
              { value: 'Asia/Dubai', label: 'Asia/Dubai (GST, UTC+04:00)' },
              { value: 'Asia/Singapore', label: 'Asia/Singapore (SGT, UTC+08:00)' },
              { value: 'Europe/London', label: 'Europe/London (GMT/BST)' },
              { value: 'America/New_York', label: 'America/New_York (EST/EDT)' },
            ]}
          />

          <Select
            label="Date Format"
            value={prefs.dateFormat}
            onChange={(e) => setPrefs((p) => ({ ...p, dateFormat: e.target.value }))}
            options={[
              { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY (e.g. 09/09/2026)' },
              { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY (e.g. 09/09/2026)' },
              { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD (ISO 8601)' },
              { value: 'D MMM YYYY', label: '09 Sep 2026 (Short Month)' },
            ]}
          />

          <Select
            label="Number & Currency Format"
            value={prefs.numberFormat}
            onChange={(e) => setPrefs((p) => ({ ...p, numberFormat: e.target.value }))}
            options={[
              { value: 'en-IN', label: 'Indian System (₹1,00,000.00)' },
              { value: 'en-US', label: 'International System ($100,000.00)' },
            ]}
          />

          <Select
            label="Currency Display Style"
            value={prefs.currencyDisplay}
            onChange={(e) => setPrefs((p) => ({ ...p, currencyDisplay: e.target.value as 'symbol' | 'code' }))}
            options={[
              { value: 'symbol', label: 'Currency Symbol (₹ / $ / €)' },
              { value: 'code', label: 'ISO Currency Code (INR / USD / EUR)' },
            ]}
          />
        </div>
      </SettingsSection>

      {/* Interface & Workspace */}
      <SettingsSection
        title="Interface & Workspace Preferences"
        description="Control default landing screens and table layout density."
      >
        <div className="space-y-4 max-w-2xl">
          <Select
            label="Default Landing Page"
            value={prefs.defaultLandingPage}
            onChange={(e) => setPrefs((p) => ({ ...p, defaultLandingPage: e.target.value }))}
            options={[
              { value: '/dashboard', label: 'Dashboard (Control Center)' },
              { value: '/invoices', label: 'Invoices' },
              { value: '/customers', label: 'Customers' },
              { value: '/subscriptions', label: 'Subscriptions' },
              { value: '/payments', label: 'Payments' },
            ]}
          />

          <div className="space-y-2 pt-2">
            <label className="block text-xs font-semibold text-slate-700">Table Display Density</label>
            <div className="grid grid-cols-2 gap-3 max-w-md">
              <button
                type="button"
                onClick={() => setPrefs((p) => ({ ...p, tableDensity: 'comfortable' }))}
                className={cn(
                  'p-3 rounded-xl border text-left cursor-pointer transition-all',
                  prefs.tableDensity === 'comfortable'
                    ? 'border-brand-600 bg-brand-50/50 text-brand-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                )}
              >
                <p className="text-xs font-semibold">Comfortable</p>
                <p className="text-[10px] text-slate-400 mt-0.5">Spacious rows with standard padding</p>
              </button>

              <button
                type="button"
                onClick={() => setPrefs((p) => ({ ...p, tableDensity: 'compact' }))}
                className={cn(
                  'p-3 rounded-xl border text-left cursor-pointer transition-all',
                  prefs.tableDensity === 'compact'
                    ? 'border-brand-600 bg-brand-50/50 text-brand-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                )}
              >
                <p className="text-xs font-semibold">Compact</p>
                <p className="text-[10px] text-slate-400 mt-0.5">High-density rows for larger screens</p>
              </button>
            </div>
          </div>

          <div className="space-y-3 pt-3 border-t border-slate-100">
            <label className="block text-xs font-semibold text-slate-700">Safety & Confirmation Dialogs</label>
            
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.confirmBeforeDelete}
                onChange={(e) => setPrefs((p) => ({ ...p, confirmBeforeDelete: e.target.checked }))}
                className="mt-0.5 w-4 h-4 text-brand-600 rounded border-slate-300 focus:ring-brand-500"
              />
              <div className="text-xs">
                <span className="font-medium text-slate-800">Confirm before deleting records</span>
                <p className="text-slate-400 text-[11px]">Displays a warning dialog before removing customers, items, or records.</p>
              </div>
            </label>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.confirmBeforeSendInvoice}
                onChange={(e) => setPrefs((p) => ({ ...p, confirmBeforeSendInvoice: e.target.checked }))}
                className="mt-0.5 w-4 h-4 text-brand-600 rounded border-slate-300 focus:ring-brand-500"
              />
              <div className="text-xs">
                <span className="font-medium text-slate-800">Confirm before sending invoices</span>
                <p className="text-slate-400 text-[11px]">Prompts confirmation prior to dispatching invoice emails and payment links to customers.</p>
              </div>
            </label>
          </div>
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
          Save Preferences
        </Button>
      </div>
    </form>
  );
}

export default PreferencesTab;
