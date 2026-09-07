import type { ReactNode } from 'react';
import { Lock } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/common/Card';

/** Read-only notice shown to viewers/finance on admin-only settings. */
export function ReadOnlyNotice({ what = 'these settings' }: { what?: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600">
      <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" />
      <span>
        Your role can view but not change {what}. Ask an owner or admin of this organization to make
        changes.
      </span>
    </div>
  );
}

export function SettingsSection({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="block">
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
      {footer && (
        <div className="px-5 py-3 bg-slate-50/75 border-t border-slate-100 flex items-center justify-end gap-2.5">
          {footer}
        </div>
      )}
    </Card>
  );
}

/** '' ⇄ null helpers for optional text fields. */
export const str = (value: string | null | undefined): string => value ?? '';
export const nullable = (value: string): string | null => (value.trim() === '' ? null : value.trim());

export interface FieldErrors {
  [field: string]: string | undefined;
}
