"""Website (landing page) content schema - the only shape a draft can take.

Mirrors frontend/src/pages/public/landing/types.ts. Everything is structured plain text:
- no field is ever rendered as HTML, and markup characters (< >) and control characters are
  refused anyway, so a draft cannot carry script or HTML payloads;
- links must be an internal path ("/..." without "//") or an absolute https:// URL - javascript:,
  data:, protocol-relative and other schemes are refused;
- icons and colour tones come from allow-lists; accent colours must be #RRGGBB;
- media must be a bundled /videos/*.mp4 file or an asset uploaded through the console
  (/uploads/website/<random>.<ext>) - no traversal, no external hosts;
- every string, list and number is bounded; unknown fields are refused (extra="forbid").

The pricing values are ILLUSTRATIVE marketing examples for the public calculator. They are not
Rooman Billing's own prices and are not connected to any tenant's Plans & Pricing.
"""
from __future__ import annotations

import re
from typing import Annotated, List, Literal, Optional, Union
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

ICON_NAMES = (
    "ArrowLeftRight", "BarChart3", "Briefcase", "Building2", "Calculator", "Calendar", "CheckCircle2",
    "CreditCard", "Cpu", "Database", "Eye", "FileText", "Layers", "Lock", "Receipt", "Server", "Shield",
    "Sliders", "Sparkles",
)
TONE_NAMES = ("indigo", "green", "pink", "orange", "lavender")
SECTION_KEYS = (
    "capabilities", "how_it_works", "workflow", "pricing", "why", "audiences", "customer_experience",
    "operations", "faq", "final_cta",
)
NAV_TARGETS = ("features", "how-it-works", "workflow", "pricing-models", "why-rooman", "faq")

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MEDIA = re.compile(r"^(/videos/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.mp4|/uploads/website/[a-f0-9]{32}\.(mp4|png|jpg|jpeg|webp))$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_PATH = re.compile(r"^/[A-Za-z0-9\-._~/%?=&#]*$")


def _text(value: str) -> str:
    if "<" in value or ">" in value:
        raise ValueError("markup characters (< >) are not allowed in website text")
    if _CONTROL.search(value):
        raise ValueError("control characters are not allowed")
    return value


def _link(value: str) -> str:
    value = value.strip()
    if value.startswith("/"):
        if value.startswith("//") or "\\" in value or not _PATH.match(value) or ".." in value:
            raise ValueError("internal links must be a plain path like /catalog")
        return value
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise ValueError("links must be an internal path (/...) or an https:// URL")
    if _CONTROL.search(value) or any(c in value for c in '<>"\' '):
        raise ValueError("invalid characters in link")
    return value


def _media(value: str) -> str:
    if not _MEDIA.match(value):
        raise ValueError("media must be a bundled /videos/*.mp4 file or an uploaded website asset")
    return value


def _hex(value: str) -> str:
    if not _HEX.match(value):
        raise ValueError("colours must be #RRGGBB")
    return value


def T(max_length: int, min_length: int = 0):
    return Annotated[str, Field(min_length=min_length, max_length=max_length), AfterValidator(_text)]


Short = T(80, 1)
Label = T(120, 1)
Title = T(160, 1)
Body = T(600, 1)
Long = T(2000, 1)
Link = Annotated[str, Field(min_length=1, max_length=300), AfterValidator(_link)]
Media = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(_media)]
Hex = Annotated[str, AfterValidator(_hex)]
Icon = Literal[ICON_NAMES]  # type: ignore[valid-type]
Tone = Literal[TONE_NAMES]  # type: ignore[valid-type]
Money = Annotated[Union[int, float], Field(ge=0, le=10_000_000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Seo(Strict):
    title: T(120, 1)
    description: T(300, 1)


class NavItem(Strict):
    target: Literal[NAV_TARGETS]  # type: ignore[valid-type]
    label: Short
    mobile_label: Short
    visible: bool = True


class Header(Strict):
    nav: List[NavItem] = Field(max_length=10)
    sign_in_label: Short
    get_started_label: Short
    dashboard_label: Short
    mobile_dashboard_label: Short


class Hero(Strict):
    visible: bool = True
    badge: Label
    headline: Title
    headline_highlight: T(160)
    subheading: Body
    primary_cta_label: Short
    secondary_cta_label: Short
    video_src: Media


class CapabilityCard(Strict):
    title: Short
    desc: Label
    link: Link
    icon: Icon
    accent: Hex
    badge_bg: Hex
    animation: Literal["catalog", "pricing", "cpq", "quotes", "invoices", "payments"]
    visible: bool = True


class Capabilities(Strict):
    visible: bool = True
    eyebrow: Short
    heading: Title
    description: Body
    cards: List[CapabilityCard] = Field(min_length=1, max_length=8)


class HowStep(Strict):
    step: T(8, 1)
    stage_label: Label
    title: Title
    desc: Body
    icon: Icon
    visible: bool = True


class HowItWorks(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    video_sources: List[Media] = Field(min_length=1, max_length=3)
    steps: List[HowStep] = Field(min_length=1, max_length=6)


class WorkflowStep(Strict):
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
    label: Short
    step: T(8, 1)
    title: Title
    desc: Body
    badge: Short
    link: Link
    details: List[Label] = Field(max_length=6)
    kpi: Label
    visible: bool = True


class Workflow(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    pause_label: Short
    resume_label: Short
    open_label: Label
    footnote: Label
    panel_title: Short
    panel_status: Short
    panel_active_label: Short
    panel_next_label: Short
    panel_metric_label: Short
    panel_validation_label: Short
    panel_validation_value: Short
    steps: List[WorkflowStep] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _unique_keys(self) -> "Workflow":
        keys = [s.key for s in self.steps]
        if len(set(keys)) != len(keys):
            raise ValueError("workflow step keys must be unique")
        return self


class Tier(Strict):
    up_to: Optional[Annotated[int, Field(ge=1, le=1_000_000)]] = None
    rate: Money


class PricingModel(Strict):
    kind: Literal["flat", "per_unit", "volume", "tiered", "package"]
    title: Short
    type: Short
    desc: Body
    example: Label
    features: List[Label] = Field(max_length=6)
    price: Optional[Money] = None
    bundle_size: Optional[Annotated[int, Field(ge=1, le=100_000)]] = None
    tiers: Optional[List[Tier]] = Field(default=None, min_length=1, max_length=6)
    visible: bool = True

    @model_validator(mode="after")
    def _parameters(self) -> "PricingModel":
        if self.kind in ("flat", "per_unit", "package") and self.price is None:
            raise ValueError(f"a {self.kind} example needs a price")
        if self.kind == "package" and self.bundle_size is None:
            raise ValueError("a package example needs a bundle size")
        if self.kind in ("volume", "tiered"):
            if not self.tiers:
                raise ValueError(f"a {self.kind} example needs tiers")
            bounds = [t.up_to for t in self.tiers]
            if any(b is None for b in bounds[:-1]):
                raise ValueError("only the last tier can be open-ended")
            finite = [b for b in bounds if b is not None]
            if finite != sorted(set(finite)):
                raise ValueError("tier limits must increase")
        return self


class Pricing(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    live_badge: Short
    live_caption: Label
    simulate_label: Short
    flat_note: Label
    calculated_label: Short
    verified_label: Short
    audit_label: Short
    isolation_label: Short
    steps_title: Short
    steps_subtitle: Label
    why_title: Short
    primary_cta_label: Short
    primary_cta_link: Link
    secondary_cta_label: Short
    secondary_cta_link: Link
    models: List[PricingModel] = Field(min_length=1, max_length=8)


class PipelineNode(Strict):
    name: Short
    icon: Icon


class IconCard(Strict):
    title: Short
    desc: Body
    icon: Icon
    tone: Tone
    visible: bool = True


class Why(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    pipeline_title: Label
    pipeline: List[PipelineNode] = Field(max_length=12)
    cards: List[IconCard] = Field(max_length=8)


class Audience(Strict):
    title: Short
    desc: Body
    icon: Icon
    benefit: Label
    example: T(300)
    visible: bool = True


class Audiences(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    items: List[Audience] = Field(max_length=8)


class ExperienceCard(Strict):
    title: Short
    desc: Body
    icon: Icon
    tone: Tone
    status_badge: Short
    footer_text: Label
    footer_link: Optional[Link] = None
    visible: bool = True


class CustomerExperience(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    cards: List[ExperienceCard] = Field(max_length=6)


class OperationsCard(IconCard):
    link: Link


class Operations(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    cards: List[OperationsCard] = Field(max_length=12)


class FaqItem(Strict):
    q: T(300, 1)
    a: Long
    visible: bool = True


class Faq(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    items: List[FaqItem] = Field(max_length=20)


class FinalCta(Strict):
    visible: bool = True
    badge: Label
    heading: Title
    description: Body
    primary_cta_label: Short
    secondary_cta_label: Short


class FooterLink(Strict):
    label: Short
    link: Link


class FooterColumn(Strict):
    title: Short
    links: List[FooterLink] = Field(max_length=12)


class Footer(Strict):
    tagline: Body
    copyright_holder: Label
    columns: List[FooterColumn] = Field(max_length=6)
    bottom_text: Label
    bottom_badges: List[Short] = Field(max_length=6)


class LandingContent(Strict):
    schema_version: Literal[1]
    seo: Seo
    header: Header
    hero: Hero
    section_order: List[Literal[SECTION_KEYS]] = Field(max_length=len(SECTION_KEYS))  # type: ignore[valid-type]
    capabilities: Capabilities
    how_it_works: HowItWorks
    workflow: Workflow
    pricing: Pricing
    why: Why
    audiences: Audiences
    customer_experience: CustomerExperience
    operations: Operations
    faq: Faq
    final_cta: FinalCta
    footer: Footer

    @model_validator(mode="after")
    def _order(self) -> "LandingContent":
        if len(set(self.section_order)) != len(self.section_order):
            raise ValueError("each section can appear only once in section_order")
        return self


# --- API models -------------------------------------------------------------------------------------------


class DraftSaveRequest(Strict):
    content: LandingContent
    revision: int = Field(ge=0, description="The draft revision this edit is based on (0 = start a new draft).")


class NoteRequest(Strict):
    note: Optional[T(300)] = None
