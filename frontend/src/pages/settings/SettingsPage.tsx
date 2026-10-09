import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  User,
  Sliders,
  Bell,
  Building2,
  Users,
  Receipt,
  CreditCard,
  Boxes,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
} from 'lucide-react';
import { PageHeader } from '../../components/common/PageHeader';
import { LoadingState } from '../../components/common/LoadingState';
import { ErrorState } from '../../components/common/ErrorState';
import { organizationService } from '../../services/organizationService';
import { toApiError } from '../../services/apiClient';
import { queryKeys } from '../../hooks/queries';
import { useAuth } from '../../hooks/useAuth';
import { cn } from '../../utils/cn';
import { OrganizationTab } from './OrganizationTab';
import { BillingTab } from './BillingTab';
import { TeamTab } from './TeamTab';
import { IntegrationsTab } from './IntegrationsTab';
import { SecurityTab } from './SecurityTab';
import { ProfileTab } from './ProfileTab';
import { PreferencesTab } from './PreferencesTab';
import { NotificationsTab } from './NotificationsTab';
import { HelpTab } from './HelpTab';
import { PlatformAccessTab } from './PlatformAccessTab';
import { usePageSpec } from '../../appUi/usePageSpec';
import { SubscriptionTab } from './SubscriptionTab';

export type SettingsTab =
  | 'profile'
  | 'preferences'
  | 'notifications'
  | 'organization'
  | 'users'
  | 'team'
  | 'billing'
  | 'subscription'
  | 'integrations'
  | 'security'
  | 'platform-access'
  | 'help';

const NAV_ICONS: Record<string, typeof User> = {
  profile: User,
  preferences: Sliders,
  notifications: Bell,
  organization: Building2,
  users: Users,
  team: Users,
  billing: Receipt,
  subscription: CreditCard,
  integrations: Boxes,
  security: ShieldCheck,
  'platform-access': ShieldAlert,
  platform_access: ShieldAlert,
  help: HelpCircle,
};

const ALL_TABS: SettingsTab[] = [
  'profile',
  'preferences',
  'notifications',
  'organization',
  'users',
  'team',
  'billing',
  'subscription',
  'integrations',
  'security',
  'platform-access',
  'help',
];

function normalizeTab(val: string | null | undefined): SettingsTab {
  if (!val) return 'profile';
  const lower = val.toLowerCase();
  if (lower === 'team') return 'users';
  if (ALL_TABS.includes(lower as SettingsTab)) return lower as SettingsTab;
  return 'profile';
}

export function SettingsPage() {
  const ui = usePageSpec('settings');
  const navigate = useNavigate();
  const params = useParams<{ section?: string; tab?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const routeTab = params.section || params.tab;
  const queryTab = searchParams.get('tab');
  const activeTab: SettingsTab = normalizeTab(routeTab || queryTab);

  const { hasRole, organization: authOrganization } = useAuth();
  const canEdit = hasRole('admin');

  const organization = useQuery({
    queryKey: queryKeys.organization.detail(),
    queryFn: organizationService.get,
    initialData: authOrganization ?? undefined,
    staleTime: 0,
  });

  const selectTab = (next: SettingsTab) => {
    if (routeTab) {
      navigate(`/settings/${next}`, { replace: true });
    } else {
      const sp = new URLSearchParams(searchParams);
      sp.set('tab', next);
      setSearchParams(sp, { replace: true });
    }
  };

  const renderOrgTab = (render: (org: NonNullable<typeof organization.data>) => JSX.Element) => {
    if (organization.isPending) return <LoadingState message="Loading organization..." />;
    if (organization.isError) {
      return <ErrorState message={toApiError(organization.error).message} onRetry={() => void organization.refetch()} />;
    }
    return render(organization.data);
  };

  return (
    <div className="space-y-6">
      <div {...ui.edit('header')}>
        <PageHeader
          title={ui.text('header', 'title')}
          subtitle={ui.text('header', 'subtitle')}
        />
      </div>

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        {/* Left Settings Navigation */}
        <nav
          aria-label="Settings navigation"
          className="w-full lg:w-64 shrink-0 bg-white rounded-xl border border-slate-200/80 p-3 space-y-4 shadow-2xs"
        >
          {/* General */}
          <div className="space-y-1" {...ui.edit('general_tabs')}>
            <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              General
            </p>
            <div className="space-y-0.5">
              {ui.shown('general_tabs').map((item) => {
                const Icon = NAV_ICONS[item.key] || User;
                const isActive = activeTab === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => selectTab(item.key as SettingsTab)}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left cursor-pointer',
                      isActive
                        ? 'bg-brand-50 text-brand-700 font-semibold shadow-2xs'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    )}
                    {...ui.edit(`general_tabs.${item.key}`)}
                  >
                    <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-brand-600' : 'text-slate-400')} />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Organization */}
          <div className="space-y-1" {...ui.edit('org_tabs')}>
            <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Organization
            </p>
            <div className="space-y-0.5">
              {ui.shown('org_tabs').map((item) => {
                const Icon = NAV_ICONS[item.key] || Building2;
                const isActive = activeTab === item.key || (item.key === 'users' && activeTab === 'team');
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => selectTab(item.key as SettingsTab)}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left cursor-pointer',
                      isActive
                        ? 'bg-brand-50 text-brand-700 font-semibold shadow-2xs'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    )}
                    {...ui.edit(`org_tabs.${item.key}`)}
                  >
                    <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-brand-600' : 'text-slate-400')} />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Security & Support */}
          <div className="space-y-1" {...ui.edit('security_tabs')}>
            <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Security & Support
            </p>
            <div className="space-y-0.5">
              {ui.shown('security_tabs').map((item) => {
                const Icon = NAV_ICONS[item.key] || ShieldCheck;
                const isActive = activeTab === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => selectTab(item.key as SettingsTab)}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left cursor-pointer',
                      isActive
                        ? 'bg-brand-50 text-brand-700 font-semibold shadow-2xs'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    )}
                    {...ui.edit(`security_tabs.${item.key}`)}
                  >
                    <Icon className={cn('w-4 h-4 shrink-0', isActive ? 'text-brand-600' : 'text-slate-400')} />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </nav>

        {/* Right Content Area */}
        <div className="flex-1 min-w-0 w-full">
          {activeTab === 'profile' && <ProfileTab />}
          {activeTab === 'preferences' && <PreferencesTab />}
          {activeTab === 'notifications' && <NotificationsTab />}
          {activeTab === 'organization' && renderOrgTab((org) => <OrganizationTab organization={org} canEdit={canEdit} />)}
          {(activeTab === 'users' || activeTab === 'team') && <TeamTab canEdit={canEdit} />}
          {activeTab === 'billing' && renderOrgTab((org) => <BillingTab organization={org} canEdit={canEdit} />)}
          {activeTab === 'subscription' && <SubscriptionTab />}
          {activeTab === 'integrations' && <IntegrationsTab />}
          {activeTab === 'security' && <SecurityTab />}
          {activeTab === 'platform-access' && (canEdit ? <PlatformAccessTab /> : (
            <ErrorState message="Only Owners and Admins can see platform access." />
          ))}
          {activeTab === 'help' && <HelpTab />}
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
