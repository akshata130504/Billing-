import { Check, Circle } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface PasswordRule {
  id: string;
  label: string;
  test: (password: string) => boolean;
}

/** Mirrors the backend policy: ≥10 chars, mixed case, at least one digit. */
export const PASSWORD_RULES: PasswordRule[] = [
  { id: 'length', label: 'At least 10 characters', test: (p) => p.length >= 10 },
  { id: 'case', label: 'Upper and lower case letters', test: (p) => /[a-z]/.test(p) && /[A-Z]/.test(p) },
  { id: 'digit', label: 'At least one digit', test: (p) => /\d/.test(p) },
];

export function passwordMeetsPolicy(password: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(password));
}

export function PasswordRules({ password, className }: { password: string; className?: string }) {
  return (
    <ul className={cn('grid grid-cols-1 sm:grid-cols-3 gap-1.5 text-[11px]', className)}>
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password);
        return (
          <li
            key={rule.id}
            className={cn('flex items-center gap-1.5', ok ? 'text-emerald-700' : 'text-slate-500')}
          >
            {ok ? (
              <Check className="w-3.5 h-3.5 shrink-0" />
            ) : (
              <Circle className="w-3 h-3 shrink-0 stroke-[1.5]" />
            )}
            <span>{rule.label}</span>
          </li>
        );
      })}
    </ul>
  );
}
