import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  User,
  Sliders,
  Bell,
  Building2,
  Users,
  Receipt,
  Boxes,
  ShieldCheck,
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

export type SettingsTab =
  | 'profile'
  | 'preferences'
  | 'notifications'
  | 'organization'
  | 'users'
  | 'team'
  | 'billing'
  | 'integrations'
  | 'security'
  | 'help';

interface NavItem {
  key: SettingsTab;
  label: string;
  icon: typeof User;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'General',
    items: [
      { key: 'profile', label: 'My Profile', icon: User },
      { key: 'preferences', label: 'Account Preferences', icon: Sliders },
      { key: 'notifications', label: 'Notifications', icon: Bell },
    ],
  },
  {
    title: 'Organization',
    items: [
      { key: 'organization', label: 'Organization', icon: Building2 },
      { key: 'users', label: 'Users & Roles', icon: Users },
      { key: 'billing', label: 'Billing & numbering', icon: Receipt },
      { key: 'integrations', label: 'Integrations', icon: Boxes },
    ],
  },
  {
    title: 'Security',
    items: [
      { key: 'security', label: 'Security', icon: ShieldCheck },
    ],
  },
  {
    title: 'Support',
    items: [
      { key: 'help', label: 'Help & Documentation', icon: HelpCircle },
    ],
  },
];

const ALL_TABS: SettingsTab[] = [
  'profile',
  'preferences',
  'notifications',
  'organization',
  'users',
  'team',
  'billing',
  'integrations',
  'security',
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
      <PageHeader
        title="Settings & Workspace Preferences"
        subtitle="Manage your profile, security, notification rules, organization profile, team members and system settings."
      />

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        {/* Left Settings Navigation */}
        <nav
          aria-label="Settings navigation"
          className="w-full lg:w-64 shrink-0 bg-white rounded-xl border border-slate-200/80 p-3 space-y-4 shadow-2xs"
        >
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="space-y-1">
              <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {group.title}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive =
                    activeTab === item.key ||
                    (item.key === 'users' && activeTab === 'team');
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => selectTab(item.key)}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left cursor-pointer',
                        isActive
                          ? 'bg-brand-50 text-brand-700 font-semibold shadow-2xs'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                      )}
                    >
                      <Icon
                        className={cn(
                          'w-4 h-4 shrink-0',
                          isActive ? 'text-brand-600' : 'text-slate-400'
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Right Content Area */}
        <div className="flex-1 min-w-0 w-full">
          {activeTab === 'profile' && <ProfileTab />}
          {activeTab === 'preferences' && <PreferencesTab />}
          {activeTab === 'notifications' && <NotificationsTab />}
          {activeTab === 'organization' && renderOrgTab((org) => <OrganizationTab organization={org} canEdit={canEdit} />)}
          {(activeTab === 'users' || activeTab === 'team') && <TeamTab canEdit={canEdit} />}
          {activeTab === 'billing' && renderOrgTab((org) => <BillingTab organization={org} canEdit={canEdit} />)}
          {activeTab === 'integrations' && <IntegrationsTab />}
          {activeTab === 'security' && <SecurityTab />}
          {activeTab === 'help' && <HelpTab />}
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
