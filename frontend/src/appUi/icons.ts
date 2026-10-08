/** Allow-listed icons for configurable UI (same list as keys.json / backend schema). */
import {
  Activity, AlertTriangle, ArrowLeftRight, BarChart3, Bell, Boxes, Briefcase, Building2, Calculator, Calendar,
  Clock, Coins, CreditCard, ExternalLink, FileCheck, FileText, Folder, Gauge, Globe, History, Inbox,
  LayoutDashboard, Layers, LineChart, Monitor, Package, Palette, Percent, PieChart, Receipt, ReceiptText,
  Repeat, Settings, ShieldCheck, Smartphone, Sparkles, Star, Tag, Target, Timer, UploadCloud, UserCheck, Users,
  Wallet, Zap, type LucideIcon,
} from 'lucide-react';
import KEYS from './keys.json';

export const UI_ICONS = {
  Activity, AlertTriangle, ArrowLeftRight, BarChart3, Bell, Boxes, Briefcase, Building2, Calculator, Calendar,
  Clock, Coins, CreditCard, ExternalLink, FileCheck, FileText, Folder, Gauge, Globe, History, Inbox,
  LayoutDashboard, Layers, LineChart, Monitor, Package, Palette, Percent, PieChart, Receipt, ReceiptText,
  Repeat, Settings, ShieldCheck, Smartphone, Sparkles, Star, Tag, Target, Timer, UploadCloud, UserCheck, Users,
  Wallet, Zap,
} satisfies Record<string, LucideIcon>;

export type UiIconName = keyof typeof UI_ICONS;
export const UI_ICON_NAMES = KEYS.icons as UiIconName[];

/** The icon for an allow-listed name, or `fallback` for anything else. */
export function uiIcon(name: string | undefined, fallback: LucideIcon): LucideIcon {
  return name && Object.prototype.hasOwnProperty.call(UI_ICONS, name) ? UI_ICONS[name as UiIconName] : fallback;
}
