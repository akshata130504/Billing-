import React from 'react';
import { Check, Copy, KeyRound, Laptop, Link2, Smartphone } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/common/Card';
import { ErrorState } from '../../components/common/ErrorState';
import { Skeleton } from '../../components/common/LoadingState';
import { useToast } from '../../components/common/Toast';
import { API_ORIGIN } from '../../services/apiClient';
import { ROLE_LABELS, formatDateTime } from '../../utils/format';
import {
  PLATFORM_FAMILIES,
  PLATFORM_LABELS,
  type MobileBootstrapOut,
  type PlatformFamily,
} from '../../types/devices';

/** Absolute API base the native clients must point at (same one this web app uses). */
export function resolveApiBaseUrl(): string {
  const origin = API_ORIGIN || (typeof window !== 'undefined' ? window.location.origin : '');
  return `${origin}/api/v1`;
}

function KeyValue({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-slate-100 last:border-0">
      <dt className="text-xs font-medium text-slate-500 shrink-0">{label}</dt>
      <dd className={`text-sm text-slate-900 text-right break-all ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  );
}

function Endpoint({ method, path }: { method: 'GET' | 'POST' | 'DELETE'; path: string }) {
  const color =
    method === 'GET' ? 'text-emerald-700 bg-emerald-50' : method === 'POST' ? 'text-blue-700 bg-blue-50' : 'text-rose-700 bg-rose-50';
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <span className={`px-1.5 py-0.5 rounded font-semibold text-[10px] ${color}`}>{method}</span>
      <span className="text-slate-800">{path}</span>
    </span>
  );
}

export interface ConnectionDetailsCardProps {
  family: PlatformFamily;
  bootstrap: MobileBootstrapOut | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function ConnectionDetailsCard({ family, bootstrap, loading, error, onRetry }: ConnectionDetailsCardProps) {
  const { showToast } = useToast();
  const apiBaseUrl = resolveApiBaseUrl();
  const [copied, setCopied] = React.useState(false);

  const copyApiUrl = async () => {
    try {
      await navigator.clipboard.writeText(apiBaseUrl);
      setCopied(true);
      showToast('success', 'API base URL copied');
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      showToast('error', 'Clipboard is not available in this browser');
    }
  };

  const exchangeExample = JSON.stringify(
    {
      email: bootstrap?.user.email ?? 'user@example.com',
      password: '••••••••',
      device: {
        device_identifier: '<stable per-install id>',
        platform: PLATFORM_FAMILIES[family][0],
        device_name: family === 'mobile' ? "Priya's iPhone" : 'Finance workstation',
        os_version: '<os version>',
        app_version: '<app version>',
        push_token: family === 'mobile' ? '<apns/fcm token, optional>' : null,
      },
    },
    null,
    2
  );

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {/* Bootstrap / connection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-brand-600" />
            Connection details
          </CardTitle>
          <CardDescription>
            Live response from <span className="font-mono text-xs">GET /mobile/bootstrap</span> — the payload a{' '}
            {family === 'mobile' ? 'mobile app' : 'desktop shell'} loads on startup.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200 mb-4">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">API base URL</div>
              <div className="font-mono text-xs text-slate-900 truncate" title={apiBaseUrl}>
                {apiBaseUrl}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={copyApiUrl}
              leadingIcon={copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            >
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>

          {loading ? (
            <div className="space-y-3 py-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-4 w-2/5" />
            </div>
          ) : error ? (
            <ErrorState title="Bootstrap unavailable" message={error} onRetry={onRetry} className="py-6" />
          ) : bootstrap ? (
            <dl>
              <KeyValue label="Organization" value={bootstrap.organization.name} />
              <KeyValue label="Slug" value={bootstrap.organization.slug} mono />
              <KeyValue label="Organization ID" value={bootstrap.organization.id} mono />
              <KeyValue
                label="Locale"
                value={`${bootstrap.organization.default_currency} · ${bootstrap.organization.timezone} · ${bootstrap.organization.country}`}
              />
              <KeyValue label="Signed in as" value={`${bootstrap.user.full_name} (${bootstrap.user.email})`} />
              <KeyValue
                label="Role"
                value={<Badge variant="primary">{ROLE_LABELS[bootstrap.membership.role] ?? bootstrap.membership.role}</Badge>}
              />
              <KeyValue
                label="Organizations available"
                value={
                  bootstrap.organizations.length === 1
                    ? bootstrap.organizations[0].name
                    : `${bootstrap.organizations.length} organizations`
                }
              />
              <KeyValue label="Server time" value={formatDateTime(bootstrap.server_time)} />
              <KeyValue
                label="Feature flags"
                value={
                  <span className="text-xs text-slate-500">
                    Not part of the bootstrap payload yet — clients derive capabilities from the membership role; every
                    billing action is authorised server-side.
                  </span>
                }
              />
            </dl>
          ) : null}
        </CardContent>
      </Card>

      {/* Native sign-in */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-brand-600" />
            {family === 'mobile' ? 'Native sign-in flow' : 'Sign in on desktop'}
          </CardTitle>
          <CardDescription>
            {family === 'mobile'
              ? 'How the iOS and Android apps obtain a session and a trusted device in one round trip.'
              : 'There are no installers published yet. The desktop shell is a thin client that talks to this API using the same native exchange as mobile.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-slate-500">Supported platforms</span>
            {PLATFORM_FAMILIES[family].map((p) => (
              <Badge key={p} variant="neutral">
                {family === 'mobile' ? <Smartphone className="w-3 h-3 mr-1" /> : <Laptop className="w-3 h-3 mr-1" />}
                {PLATFORM_LABELS[p]}
              </Badge>
            ))}
          </div>

          <ol className="space-y-3 text-sm text-slate-700">
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold flex items-center justify-center">1</span>
              <div>
                <Endpoint method="POST" path="/auth/native/exchange" />
                <p className="text-xs text-slate-500 mt-1">
                  Sends email, password and the device descriptor. Authenticates exactly like the web login (same rate
                  limit) and registers or refreshes the device in the same call. New devices are trusted immediately.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold flex items-center justify-center">2</span>
              <div>
                <span className="text-sm">Receive tokens and the device record</span>
                <p className="text-xs text-slate-500 mt-1">
                  Response carries <span className="font-mono">access_token</span>,{' '}
                  <span className="font-mono">refresh_token</span>, <span className="font-mono">expires_in</span> (access-token
                  lifetime in seconds) and the <span className="font-mono">device</span>. Store both tokens in OS secure storage.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold flex items-center justify-center">3</span>
              <div>
                <Endpoint method="GET" path="/mobile/bootstrap" />
                <p className="text-xs text-slate-500 mt-1">
                  With <span className="font-mono">Authorization: Bearer</span> — returns the user, organization, membership and
                  organization list shown on the left. Then call the shared billing APIs; nothing is duplicated client-side.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold flex items-center justify-center">4</span>
              <div>
                <Endpoint method="POST" path="/auth/refresh" />
                <p className="text-xs text-slate-500 mt-1">
                  Rotates the refresh token when the access token expires. <Endpoint method="POST" path="/devices" /> keeps{' '}
                  <span className="font-mono">last_seen_at</span>, app version and push token current on each launch.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-rose-50 text-rose-700 text-xs font-semibold flex items-center justify-center">5</span>
              <div>
                <Endpoint method="DELETE" path="/devices/{id}" />
                <p className="text-xs text-slate-500 mt-1">
                  Revokes a device (lost {family === 'mobile' ? 'phone' : 'laptop'}, offboarding): its push token is cleared and
                  the identifier can no longer be re-registered. Pair with <Endpoint method="POST" path="/auth/logout" /> to
                  revoke the refresh token.
                </p>
              </div>
            </li>
          </ol>

          <div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Exchange request body</div>
            <pre className="text-[11px] leading-relaxed font-mono bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto">
              {exchangeExample}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
