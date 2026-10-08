import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppWindow, Hash, LayoutTemplate, Tags, Webhook } from 'lucide-react';
import { PageHeader } from '../../components/common/PageHeader';
import { StatCard } from '../../components/common/StatCard';
import { useAuth } from '../../hooks/useAuth';
import { customizationService } from '../../services/customizationService';
import { cn } from '../../utils/cn';
import type { DocumentTemplate, NumberSeries, ReportingTag, WebhookDelivery, WebTab } from '../../types/customization';
import { DocumentTemplatesTab } from './DocumentTemplatesTab';
import { ReportingTagsTab } from './ReportingTagsTab';
import { NumberSeriesTab } from './NumberSeriesTab';
import { WebTabsTab } from './WebTabsTab';
import { WebhookDeliveriesTab } from './WebhookDeliveriesTab';
import { useResource } from './shared';
import { usePageSpec } from '../../appUi/usePageSpec';

export type CustomizationTab = 'templates' | 'tags' | 'number-series' | 'web-tabs' | 'webhooks';

const TAB_ICONS: Record<string, typeof LayoutTemplate> = {
  templates: LayoutTemplate,
  tags: Tags,
  'number-series': Hash,
  'web-tabs': AppWindow,
  webhooks: Webhook,
};

const TABS: { key: CustomizationTab; label: string; icon: typeof LayoutTemplate }[] = [
  { key: 'templates', label: 'Document templates', icon: LayoutTemplate },
  { key: 'tags', label: 'Reporting tags', icon: Tags },
  { key: 'number-series', label: 'Number series', icon: Hash },
  { key: 'web-tabs', label: 'Web tabs', icon: AppWindow },
  { key: 'webhooks', label: 'Webhook deliveries', icon: Webhook },
];

function isTab(value: string | null): value is CustomizationTab {
  return TABS.some((t) => t.key === value);
}

export function CustomizationPage() {
  const ui = usePageSpec('customization');
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('tab');
  const tab: CustomizationTab = isTab(rawTab) ? rawTab : 'templates';

  const { hasRole } = useAuth();
  // Templates, tags, number series and web tabs are admin-only writes on the API;
  // webhook retries are allowed from the finance role upwards.
  const canManage = hasRole('admin');
  const canRetry = hasRole('finance');

  // Stable fetchers so useResource does not refetch on every render.
  const fetchTemplates = useCallback(() => customizationService.listTemplates(), []);
  const fetchTags = useCallback(() => customizationService.listReportingTags(), []);
  const fetchSeries = useCallback(() => customizationService.listNumberSeries(), []);
  const fetchWebTabs = useCallback(() => customizationService.listWebTabs(), []);
  const fetchDeliveries = useCallback(() => customizationService.listWebhookDeliveries(), []);

  const templates = useResource<DocumentTemplate>(fetchTemplates);
  const tags = useResource<ReportingTag>(fetchTags);
  const series = useResource<NumberSeries>(fetchSeries);
  const webTabs = useResource<WebTab>(fetchWebTabs);
  const deliveries = useResource<WebhookDelivery>(fetchDeliveries);

  const selectTab = (next: CustomizationTab) => {
    const params = new URLSearchParams(searchParams);
    params.set('tab', next);
    setSearchParams(params, { replace: true });
  };

  const failedDeliveries = deliveries.items.filter((d) => d.status === 'failed').length;
  const defaultTemplates = templates.items.filter((t) => t.is_default).length;
  const activeTags = tags.items.filter((t) => t.is_active).length;
  const activeSeries = series.items.filter((s) => s.is_active).length;
  const activeWebTabs = webTabs.items.filter((t) => t.is_active).length;

  const statValue = (loading: boolean, value: number) => (loading ? '…' : value);

  return (
    <div className="space-y-6 pb-12">
      <div {...ui.edit('header')}>
        <PageHeader
          eyebrow={ui.text('header', 'eyebrow')}
          title={ui.text('header', 'title')}
          subtitle={ui.text('header', 'subtitle')}
        />
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4" {...ui.edit('kpis')}>
        {ui.render('kpis', {
          templates: (item, edit) => (
            <div key="templates" {...edit}>
              <StatCard
                title={item.label}
                value={statValue(templates.loading, templates.items.length)}
                comparisonText={templates.loading ? undefined : `${defaultTemplates} set as default`}
                icon={<LayoutTemplate className="w-4 h-4" />}
              />
            </div>
          ),
          tags: (item, edit) => (
            <div key="tags" {...edit}>
              <StatCard
                title={item.label}
                value={statValue(tags.loading, tags.items.length)}
                comparisonText={tags.loading ? undefined : `${activeTags} active`}
                icon={<Tags className="w-4 h-4" />}
              />
            </div>
          ),
          series: (item, edit) => (
            <div key="series" {...edit}>
              <StatCard
                title={item.label}
                value={statValue(series.loading, series.items.length)}
                comparisonText={series.loading ? undefined : `${activeSeries} active`}
                icon={<Hash className="w-4 h-4" />}
              />
            </div>
          ),
          tabs: (item, edit) => (
            <div key="tabs" {...edit}>
              <StatCard
                title={item.label}
                value={statValue(webTabs.loading, webTabs.items.length)}
                comparisonText={webTabs.loading ? undefined : `${activeWebTabs} visible`}
                icon={<AppWindow className="w-4 h-4" />}
              />
            </div>
          ),
          deliveries: (item, edit) => (
            <div key="deliveries" {...edit}>
              <StatCard
                title={item.label}
                value={statValue(deliveries.loading, failedDeliveries)}
                comparisonText={deliveries.loading ? undefined : `of ${deliveries.items.length} deliveries`}
                isPositive={failedDeliveries === 0}
                icon={<Webhook className="w-4 h-4" />}
              />
            </div>
          ),
        })}
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <nav className="-mb-px flex gap-1 overflow-x-auto" aria-label="Customization sections" role="tablist" {...ui.edit('tabs')}>
          {ui.shown('tabs').map((t) => {
            const Icon = TAB_ICONS[t.key] || LayoutTemplate;
            const active = t.key === tab;
            const badge = t.key === 'webhooks' && failedDeliveries > 0 ? failedDeliveries : null;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => selectTab(t.key as CustomizationTab)}
                className={cn(
                  'inline-flex items-center gap-2 px-3.5 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors',
                  active
                    ? 'border-brand-600 text-brand-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
                )}
                {...ui.edit(`tabs.${t.key}`)}
              >
                <Icon className={cn('w-4 h-4 shrink-0', active ? 'text-brand-600' : 'text-slate-400')} />
                {t.label}
                {badge !== null && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-rose-100 text-rose-700 text-[11px] font-semibold tabular-nums">
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <div role="tabpanel">
        {tab === 'templates' && <DocumentTemplatesTab resource={templates} canManage={canManage} />}
        {tab === 'tags' && <ReportingTagsTab resource={tags} canManage={canManage} />}
        {tab === 'number-series' && <NumberSeriesTab resource={series} canManage={canManage} />}
        {tab === 'web-tabs' && <WebTabsTab resource={webTabs} canManage={canManage} />}
        {tab === 'webhooks' && <WebhookDeliveriesTab resource={deliveries} canRetry={canRetry} />}
      </div>
    </div>
  );
}
