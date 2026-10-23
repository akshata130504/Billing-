import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Plus, RefreshCw, Search, ShieldOff, Smartphone } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { StatCard } from '../../components/common/StatCard';
import { LoadingState } from '../../components/common/LoadingState';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorState } from '../../components/common/ErrorState';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { useAuth } from '../../hooks/useAuth';
import { deviceService } from '../../services/deviceService';
import {
  PLATFORM_FAMILIES,
  PLATFORM_LABELS,
  TRUST_STATUS_LABELS,
  type DeviceOut,
  type DevicePlatform,
  type DeviceTrustStatus,
  type MobileBootstrapOut,
  type PlatformFamily,
} from '../../types/devices';
import { DevicesTable } from './DevicesTable';
import { RegisterDeviceModal } from './RegisterDeviceModal';
import { ConnectionDetailsCard } from './ConnectionDetailsCard';
import { usePageSpec } from '../../appUi/usePageSpec';
import { fillTokens } from '../../appUi/registry';

const ACTIVE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

export interface PlatformPageProps {
  family: PlatformFamily;
  /** Visual-editor page spec ('mobile' / 'desktop'): each platform page is configured on its own. */
  uiKey: 'mobile' | 'desktop';
  icon: React.ReactNode;
}

export function PlatformPage({ family, uiKey, icon }: PlatformPageProps) {
  const { showToast } = useToast();
  const ui = usePageSpec(uiKey);
  const { user } = useAuth();
  // POST /devices and DELETE /devices/{id} require no particular role — any authenticated
  // org member can register or revoke their own device.
  const canWrite = true;
  const familyPlatforms = PLATFORM_FAMILIES[family];

  const [devices, setDevices] = useState<DeviceOut[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(true);
  const [devicesError, setDevicesError] = useState<string | null>(null);

  const [bootstrap, setBootstrap] = useState<MobileBootstrapOut | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | DeviceTrustStatus>('all');
  const [platformFilter, setPlatformFilter] = useState<'all' | DevicePlatform>('all');

  const [registerOpen, setRegisterOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<DeviceOut | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadDevices = useCallback(async () => {
    try {
      setDevicesLoading(true);
      setDevicesError(null);
      setDevices(await deviceService.list());
    } catch (err: any) {
      setDevicesError(err.message || 'Failed to load devices');
    } finally {
      setDevicesLoading(false);
    }
  }, []);

  const loadBootstrap = useCallback(async () => {
    try {
      setBootstrapLoading(true);
      setBootstrapError(null);
      setBootstrap(await deviceService.bootstrap());
    } catch (err: any) {
      setBootstrapError(err.message || 'Failed to load bootstrap details');
    } finally {
      setBootstrapLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDevices();
    void loadBootstrap();
  }, [loadDevices, loadBootstrap]);

  const familyDevices = useMemo(
    () => devices.filter((d) => familyPlatforms.includes(d.platform)),
    [devices, familyPlatforms]
  );

  const stats = useMemo(() => {
    const cutoff = Date.now() - ACTIVE_WINDOW_MS;
    let active = 0;
    let revoked = 0;
    familyDevices.forEach((d) => {
      if (d.trust_status === 'revoked') {
        revoked += 1;
        return;
      }
      if (d.last_seen_at && new Date(d.last_seen_at).getTime() >= cutoff) active += 1;
    });
    return { registered: familyDevices.length, active, revoked };
  }, [familyDevices]);

  const visibleDevices = useMemo(() => {
    const q = search.trim().toLowerCase();
    return familyDevices.filter((d) => {
      if (statusFilter !== 'all' && d.trust_status !== statusFilter) return false;
      if (platformFilter !== 'all' && d.platform !== platformFilter) return false;
      if (!q) return true;
      return (
        (d.device_name ?? '').toLowerCase().includes(q) ||
        d.device_identifier.toLowerCase().includes(q) ||
        (d.app_version ?? '').toLowerCase().includes(q)
      );
    });
  }, [familyDevices, search, statusFilter, platformFilter]);

  const hasFilters = search.trim() !== '' || statusFilter !== 'all' || platformFilter !== 'all';

  const handleRefresh = () => {
    void loadDevices();
    void loadBootstrap();
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    const target = revokeTarget;
    try {
      setRevokingId(target.id);
      const res = await deviceService.revoke(target.id);
      showToast('success', res.message || `Revoked ${target.device_name || PLATFORM_LABELS[target.platform]} device`);
      setRevokeTarget(null);
      await loadDevices();
    } catch (err: any) {
      showToast('error', err.message || 'Failed to revoke device');
    } finally {
      setRevokingId(null);
    }
  };

  const registeredBy = user?.full_name || user?.email || 'You';
  const platformList = familyPlatforms.map((p) => PLATFORM_LABELS[p]).join(' · ');
  const platformChoices = familyPlatforms.map((p) => PLATFORM_LABELS[p]).join(' or ');

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div {...ui.edit('header')}>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            {icon}
            {ui.text('header', 'eyebrow')}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{ui.text('header', 'title')}</h1>
          <p className="text-sm text-slate-500 mt-1">{ui.text('header', 'subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} leadingIcon={<RefreshCw className="w-4 h-4" />}>
            Refresh
          </Button>
          {canWrite && (
            <Button variant="primary" size="sm" onClick={() => setRegisterOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
              Register device
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4" {...ui.edit('stats')}>
        {ui.render('stats', {
          registered: (item, edit) => (
            <div className="grid" {...edit}>
              <StatCard
                title={item.label}
                value={devicesLoading ? '—' : stats.registered}
                comparisonText={fillTokens(item.caption ?? '', { platforms: platformList })}
                icon={<Smartphone className="w-4 h-4" />}
              />
            </div>
          ),
          active: (item, edit) => (
            <div className="grid" {...edit}>
              <StatCard
                title={item.label}
                value={devicesLoading ? '—' : stats.active}
                comparisonText={item.caption}
                icon={<Activity className="w-4 h-4" />}
              />
            </div>
          ),
          revoked: (item, edit) => (
            <div className="grid" {...edit}>
              <StatCard
                title={item.label}
                value={devicesLoading ? '—' : stats.revoked}
                comparisonText={item.caption}
                icon={<ShieldOff className="w-4 h-4" />}
              />
            </div>
          ),
        })}
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm" {...ui.edit('filters')}>
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder={ui.text('filters', 'search_placeholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
            />
          </div>
          <div className="flex items-center gap-2 w-full md:w-auto">
            <select
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value as 'all' | DevicePlatform)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">{ui.text('filters', 'all_platforms')}</option>
              {familyPlatforms.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABELS[p]}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | DeviceTrustStatus)}
              className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">{ui.text('filters', 'all_statuses')}</option>
              {(Object.keys(TRUST_STATUS_LABELS) as DeviceTrustStatus[]).map((s) => (
                <option key={s} value={s}>
                  {TRUST_STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Devices table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between" {...ui.edit('devices')}>
          <h2 className="text-sm font-semibold text-slate-900">{ui.text('devices', 'title')}</h2>
          {!devicesLoading && !devicesError && (
            <span className="text-xs text-slate-500">
              {ui.text('devices', 'count', { shown: String(visibleDevices.length), total: String(familyDevices.length) })}
            </span>
          )}
        </div>
        {devicesLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-8">
            <LoadingState message={`Loading ${family} devices...`} />
          </div>
        ) : devicesError ? (
          <ErrorState title="Devices could not be loaded" message={devicesError} onRetry={() => void loadDevices()} />
        ) : familyDevices.length === 0 ? (
          <div {...ui.edit('empty')}>
            <EmptyState
              icon={icon}
              title={ui.text('empty', 'title')}
              description={
                canWrite
                  ? ui.text('empty', 'description', { platforms: platformChoices })
                  : `Devices appear here once a ${platformChoices} client signs in through the native exchange.`
              }
              action={
                canWrite ? (
                  <Button variant="primary" size="sm" onClick={() => setRegisterOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
                    Register device
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : visibleDevices.length === 0 ? (
          <div {...ui.edit('empty')}>
            <EmptyState
              title={ui.text('empty', 'filtered_title')}
              description={ui.text('empty', 'filtered_description')}
              action={
                hasFilters ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSearch('');
                      setStatusFilter('all');
                      setPlatformFilter('all');
                    }}
                  >
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <DevicesTable
              devices={visibleDevices}
              registeredBy={registeredBy}
              canWrite={canWrite}
              onRevoke={setRevokeTarget}
              revokingId={revokingId}
              columns={ui.shown('columns')}
              edit={ui.edit}
            />
          </div>
        )}
      </div>

      {/* Connection details + native sign-in */}
      <ConnectionDetailsCard
        family={family}
        bootstrap={bootstrap}
        loading={bootstrapLoading}
        error={bootstrapError}
        onRetry={() => void loadBootstrap()}
        texts={{
          title: ui.text('connection', 'title'),
          signInTitle: ui.text('connection', 'sign_in_title'),
          signInDescription: ui.text('connection', 'sign_in_description'),
        }}
        editProps={ui.edit('connection')}
      />

      <RegisterDeviceModal
        isOpen={registerOpen}
        onClose={() => setRegisterOpen(false)}
        platforms={familyPlatforms}
        onRegistered={() => void loadDevices()}
      />

      <ConfirmDialog
        isOpen={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={handleRevoke}
        title="Revoke this device?"
        description={
          revokeTarget
            ? `${revokeTarget.device_name || 'This device'} (${PLATFORM_LABELS[revokeTarget.platform]}) will be marked revoked and its push token cleared. The identifier "${revokeTarget.device_identifier}" cannot be registered again.`
            : undefined
        }
        confirmLabel="Revoke device"
        variant="danger"
        isLoading={revokingId !== null}
      />
    </div>
  );
}
