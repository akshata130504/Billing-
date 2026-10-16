import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { SCOPE_LABELS, platformAccessService } from '../../services/platformAccessService';

/**
 * Shown to Owners and Admins while Rooman platform support has approved access to this
 * organization (design section 11). Renders nothing otherwise, and never blocks the page.
 */
export function PlatformAccessBanner() {
  const { hasRole, isAuthenticated } = useAuth();
  const enabled = isAuthenticated && hasRole('admin');
  const active = useQuery({
    queryKey: ['platform-access-active'],
    queryFn: platformAccessService.active,
    enabled,
    refetchInterval: 60_000,
    retry: false,
  });
  if (!enabled || !active.data || active.data.length === 0) return null;
  return (
    <div role="status" className="no-print border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">
      {active.data.map((g) => (
        <p key={g.id} className="flex flex-wrap items-center gap-1">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          <strong>Rooman Platform {g.is_emergency ? 'emergency access' : 'Support'}</strong>
          ({g.requested_by?.full_name ?? 'staff'}) has read access to {g.scopes.filter((s) => s !== 'READ_METADATA').map((s) => SCOPE_LABELS[s] ?? s).join(', ') || 'organization details'}
          {g.expires_at ? ` until ${new Date(g.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''} - ticket {g.ticket_ref}.
          <Link to="/settings/platform-access" className="ml-1 font-semibold underline">Review or revoke</Link>
        </p>
      ))}
    </div>
  );
}
