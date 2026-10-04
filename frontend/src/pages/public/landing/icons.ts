/**
 * The only icons and color tones website content may reference (by name). Content can never
 * inject markup or arbitrary components; the backend validates the same allow-lists.
 */
import {
  ArrowLeftRight,
  BarChart3,
  Briefcase,
  Building2,
  Calculator,
  Calendar,
  CheckCircle2,
  CreditCard,
  Cpu,
  Database,
  Eye,
  FileText,
  Layers,
  Lock,
  Receipt,
  Server,
  Shield,
  Sliders,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

export const ICONS = {
  ArrowLeftRight,
  BarChart3,
  Briefcase,
  Building2,
  Calculator,
  Calendar,
  CheckCircle2,
  CreditCard,
  Cpu,
  Database,
  Eye,
  FileText,
  Layers,
  Lock,
  Receipt,
  Server,
  Shield,
  Sliders,
  Sparkles,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;
export const ICON_NAMES = Object.keys(ICONS) as IconName[];

export function iconFor(name: string): LucideIcon {
  return (ICONS as Record<string, LucideIcon>)[name] ?? Layers;
}

/** Icon tile colors used on the landing page (exact class strings from the original page). */
export const TONES = {
  indigo: 'bg-[#E8EBFC] text-[#3F51C9]',
  green: 'bg-[#DDF4EA] text-[#107548]',
  pink: 'bg-[#F9D9E8] text-[#D81B60]',
  orange: 'bg-[#FCEBD9] text-[#C05621]',
  lavender: 'bg-[#E9E8FA] text-[#25247A]',
} as const;

export type ToneName = keyof typeof TONES;
export const TONE_NAMES = Object.keys(TONES) as ToneName[];

export function toneFor(name: string): string {
  return (TONES as Record<string, string>)[name] ?? TONES.indigo;
}
