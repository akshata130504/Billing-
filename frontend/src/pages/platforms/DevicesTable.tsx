import { ShieldOff } from 'lucide-react';
import { Badge, type BadgeProps } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { formatDateTime, formatRelative } from '../../utils/format';
import {
  PLATFORM_LABELS,
  TRUST_STATUS_LABELS,
  type DeviceOut,
  type DevicePlatform,
  type DeviceTrustStatus,
} from '../../types/devices';

type BadgeVariant = NonNullable<BadgeProps['variant']>;

const PLATFORM_BADGE: Record<DevicePlatform, BadgeVariant> = {
  ios: 'info',
  android: 'success',
  windows: 'primary',
  macos: 'neutral',
};

const STATUS_BADGE: Record<DeviceTrustStatus, BadgeVariant> = {
  trusted: 'success',
  pending: 'warning',
  revoked: 'danger',
};

export interface DevicesTableProps {
  devices: DeviceOut[];
  /** Display name of the account that owns these devices (GET /devices is scoped to the caller). */
  registeredBy: string;
  canWrite: boolean;
  onRevoke: (device: DeviceOut) => void;
  revokingId?: string | null;
}

export function DevicesTable({ devices, registeredBy, canWrite, onRevoke, revokingId }: DevicesTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm text-slate-600">
        <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
          <tr>
            <th className="px-5 py-3.5">Device</th>
            <th className="px-5 py-3.5">Platform</th>
            <th className="px-5 py-3.5">App version</th>
            <th className="px-5 py-3.5">Last seen</th>
            <th className="px-5 py-3.5">Registered</th>
            <th className="px-5 py-3.5">Status</th>
            {canWrite && <th className="px-5 py-3.5 text-right">Actions</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {devices.map((device) => {
            const isRevoked = device.trust_status === 'revoked';
            return (
              <tr key={device.id} className={isRevoked ? 'bg-slate-50/40' : 'hover:bg-slate-50/70 transition-colors'}>
                <td className="px-5 py-4">
                  <div className={`font-semibold ${isRevoked ? 'text-slate-500' : 'text-slate-900'}`}>
                    {device.device_name || <span className="italic text-slate-400">Unnamed device</span>}
                  </div>
                  <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-[16rem]" title={device.device_identifier}>
                    {device.device_identifier}
                  </div>
                </td>
                <td className="px-5 py-4">
                  <div className="flex flex-col items-start gap-1">
                    <Badge variant={PLATFORM_BADGE[device.platform] ?? 'neutral'}>
                      {PLATFORM_LABELS[device.platform] ?? device.platform}
                    </Badge>
                    {device.os_version && <span className="text-xs text-slate-400">OS {device.os_version}</span>}
                  </div>
                </td>
                <td className="px-5 py-4 text-slate-700 font-medium tabular-nums">
                  {device.app_version || <span className="text-slate-400">—</span>}
                </td>
                <td className="px-5 py-4">
                  {device.last_seen_at ? (
                    <>
                      <div className="text-slate-700 font-medium">{formatRelative(device.last_seen_at)}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{formatDateTime(device.last_seen_at)}</div>
                    </>
                  ) : (
                    <span className="text-slate-400">Never</span>
                  )}
                </td>
                <td className="px-5 py-4">
                  <div className="text-slate-700">{registeredBy}</div>
                  <div className="text-xs text-slate-400 mt-0.5">{formatDateTime(device.created_at)}</div>
                </td>
                <td className="px-5 py-4">
                  <Badge variant={STATUS_BADGE[device.trust_status] ?? 'neutral'} dot>
                    {TRUST_STATUS_LABELS[device.trust_status] ?? device.trust_status}
                  </Badge>
                  {isRevoked && device.revoked_at && (
                    <div className="text-xs text-slate-400 mt-1">{formatDateTime(device.revoked_at)}</div>
                  )}
                </td>
                {canWrite && (
                  <td className="px-5 py-4 text-right">
                    {!isRevoked && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                        onClick={() => onRevoke(device)}
                        isLoading={revokingId === device.id}
                        leadingIcon={<ShieldOff className="w-3.5 h-3.5" />}
                      >
                        Revoke
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
