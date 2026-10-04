/**
 * Landing page content model (platform-managed CMS, see docs/platform-console.md).
 * Mirrors backend/app/schemas/website.py, which validates every draft before it can be saved.
 * Plain text only - React escapes everything; no field is ever rendered as HTML.
 */
import type { IconName, ToneName } from './icons';

export type SectionKey =
  | 'capabilities' | 'how_it_works' | 'workflow' | 'pricing' | 'why'
  | 'audiences' | 'customer_experience' | 'operations' | 'faq' | 'final_cta';

export type NavTarget = 'features' | 'how-it-works' | 'workflow' | 'pricing-models' | 'why-rooman' | 'faq';
export type CapabilityAnimation = 'catalog' | 'pricing' | 'cpq' | 'quotes' | 'invoices' | 'payments';

export interface Tier {
  up_to: number | null;
  rate: number;
}

export interface PricingModel {
  kind: 'flat' | 'per_unit' | 'volume' | 'tiered' | 'package';
  title: string;
  type: string;
  desc: string;
  example: string;
  features: string[];
  /** flat: monthly fee; per_unit: unit price; package: bundle price */
  price?: number;
  bundle_size?: number;
  tiers?: Tier[];
  visible: boolean;
}

export interface LandingContent {
  schema_version: 1;
  seo: { title: string; description: string };
  header: {
    nav: { target: NavTarget; label: string; mobile_label: string; visible: boolean }[];
    sign_in_label: string;
    get_started_label: string;
    dashboard_label: string;
    mobile_dashboard_label: string;
  };
  hero: {
    visible: boolean;
    badge: string;
    headline: string;
    headline_highlight: string;
    subheading: string;
    primary_cta_label: string;
    secondary_cta_label: string;
    video_src: string;
  };
  section_order: SectionKey[];
  capabilities: {
    visible: boolean;
    eyebrow: string;
    heading: string;
    description: string;
    cards: {
      title: string; desc: string; link: string; icon: IconName; accent: string; badge_bg: string;
      animation: CapabilityAnimation; visible: boolean;
    }[];
  };
  how_it_works: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    video_sources: string[];
    steps: { step: string; stage_label: string; title: string; desc: string; icon: IconName; visible: boolean }[];
  };
  workflow: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    pause_label: string;
    resume_label: string;
    open_label: string;
    footnote: string;
    panel_title: string;
    panel_status: string;
    panel_active_label: string;
    panel_next_label: string;
    panel_metric_label: string;
    panel_validation_label: string;
    panel_validation_value: string;
    steps: {
      key: string; label: string; step: string; title: string; desc: string; badge: string; link: string;
      details: string[]; kpi: string; visible: boolean;
    }[];
  };
  pricing: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    live_badge: string;
    live_caption: string;
    simulate_label: string;
    flat_note: string;
    calculated_label: string;
    verified_label: string;
    audit_label: string;
    isolation_label: string;
    steps_title: string;
    steps_subtitle: string;
    why_title: string;
    primary_cta_label: string;
    primary_cta_link: string;
    secondary_cta_label: string;
    secondary_cta_link: string;
    models: PricingModel[];
  };
  why: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    pipeline_title: string;
    pipeline: { name: string; icon: IconName }[];
    cards: { title: string; desc: string; icon: IconName; tone: ToneName; visible: boolean }[];
  };
  audiences: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    items: { title: string; desc: string; icon: IconName; benefit: string; example: string; visible: boolean }[];
  };
  customer_experience: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    cards: {
      title: string; desc: string; icon: IconName; tone: ToneName; status_badge: string; footer_text: string;
      footer_link: string | null; visible: boolean;
    }[];
  };
  operations: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    cards: { title: string; desc: string; icon: IconName; tone: ToneName; link: string; visible: boolean }[];
  };
  faq: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    items: { q: string; a: string; visible: boolean }[];
  };
  final_cta: {
    visible: boolean;
    badge: string;
    heading: string;
    description: string;
    primary_cta_label: string;
    secondary_cta_label: string;
  };
  footer: {
    tagline: string;
    copyright_holder: string;
    columns: { title: string; links: { label: string; link: string }[] }[];
    bottom_text: string;
    bottom_badges: string[];
  };
}
