import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Building2, Receipt, Users, Boxes, ShieldCheck } from 'lucide-react';
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

export type SettingsTab = 'organization' | 'billing' | 'team' | 'integrations' | 'security';

const TABS: { key: SettingsTab; label: string; icon: typeof Building2 }[] = [
  { key: 'organization', label: 'Organization', icon: Building2 },
  { key: 'billing', label: 'Billing & numbering', icon: Receipt },
  { key: 'team', label: 'Team', icon: Users },
  { key: 'integrations', label: 'Integrations', icon: Boxes },
  { key: 'security', label: 'Security', icon: ShieldCheck },
];

function isTab(value: string | null): value is SettingsTab {
  return TABS.some((t) => t.key === value);
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('tab');
  const tab: SettingsTab = isTab(rawTab) ? rawTab : 'organization';
  const { hasRole, organization: authOrganization } = useAuth();
  const canEdit = hasRole('admin');

  const organization = useQuery({
    queryKey: queryKeys.organization.detail(),
    queryFn: organizationService.get,
    initialData: authOrganization ?? undefined,
    // Always confirm against the server on mount so edits from elsewhere show up.
    staleTime: 0,
  });

  const selectTab = (next: SettingsTab) => {
    const params = new URLSearchParams(searchParams);
    params.set('tab', next);
    setSearchParams(params, { replace: true });
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
        title="Settings"
        subtitle="Organization profile, billing defaults, team access, integrations and your account security."
      />

      <div className="flex flex-col lg:flex-row gap-6">
        <nav
          aria-label="Settings sections"
          className="lg:w-56 shrink-0 flex lg:flex-col gap-1 overflow-x-auto pb-1 lg:pb-0"
        >
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = t.key === tab;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => selectTab(t.key)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors text-left',
                  active
                    ? 'bg-brand-50 text-brand-700 font-semibold'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                )}
              >
                <Icon className={cn('w-4 h-4 shrink-0', active ? 'text-brand-600' : 'text-slate-400')} />
                {t.label}
              </button>
            );
          })}
        </nav>

        <div className="flex-1 min-w-0">
          {tab === 'organization' && renderOrgTab((org) => <OrganizationTab organization={org} canEdit={canEdit} />)}
          {tab === 'billing' && renderOrgTab((org) => <BillingTab organization={org} canEdit={canEdit} />)}
          {tab === 'team' && <TeamTab canEdit={canEdit} />}
          {tab === 'integrations' && <IntegrationsTab />}
          {tab === 'security' && <SecurityTab />}
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
