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

const ACTIVE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

export interface PlatformPageProps {
  family: PlatformFamily;
  title: string;
  subtitle: string;
  icon: React.ReactNode;
}

export function PlatformPage({ family, title, subtitle, icon }: PlatformPageProps) {
  const { showToast } = useToast();
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

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider mb-1">
            {icon}
            Platforms
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h1>
          <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Registered devices"
          value={devicesLoading ? '—' : stats.registered}
          comparisonText={familyPlatforms.map((p) => PLATFORM_LABELS[p]).join(' · ')}
          icon={<Smartphone className="w-4 h-4" />}
        />
        <StatCard
          title="Active (30 days)"
          value={devicesLoading ? '—' : stats.active}
          comparisonText="Trusted devices seen in the last 30 days"
          icon={<Activity className="w-4 h-4" />}
        />
        <StatCard
          title="Revoked"
          value={devicesLoading ? '—' : stats.revoked}
          comparisonText="Records kept for audit; identifiers cannot be re-used"
          icon={<ShieldOff className="w-4 h-4" />}
        />
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="relative flex-1 w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search device name, identifier, app version..."
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
              <option value="all">All platforms</option>
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
              <option value="all">All statuses</option>
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
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Registered devices</h2>
          {!devicesLoading && !devicesError && (
            <span className="text-xs text-slate-500">
              {visibleDevices.length} of {familyDevices.length} · your devices in this organization
            </span>
          )}
        </div>
        {devicesLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm py-8">
            <LoadingState message={`Loading ${title.toLowerCase()} devices...`} />
          </div>
        ) : devicesError ? (
          <ErrorState title="Devices could not be loaded" message={devicesError} onRetry={() => void loadDevices()} />
        ) : familyDevices.length === 0 ? (
          <EmptyState
            icon={icon}
            title={`No ${title.toLowerCase()} devices registered`}
            description={
              canWrite
                ? `Devices appear here once a ${familyPlatforms.map((p) => PLATFORM_LABELS[p]).join(' or ')} client signs in through the native exchange, or you can register one manually.`
                : `Devices appear here once a ${familyPlatforms.map((p) => PLATFORM_LABELS[p]).join(' or ')} client signs in through the native exchange.`
            }
            action={
              canWrite ? (
                <Button variant="primary" size="sm" onClick={() => setRegisterOpen(true)} leadingIcon={<Plus className="w-4 h-4" />}>
                  Register device
                </Button>
              ) : undefined
            }
          />
        ) : visibleDevices.length === 0 ? (
          <EmptyState
            title="No devices match these filters"
            description="Try a different platform, status or search term."
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
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <DevicesTable
              devices={visibleDevices}
              registeredBy={registeredBy}
              canWrite={canWrite}
              onRevoke={setRevokeTarget}
              revokingId={revokingId}
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
