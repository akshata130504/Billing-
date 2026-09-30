import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LandingView } from '../LandingView';
import { DEFAULT_LANDING_CONTENT, isLandingContent } from './content';
import { buildBreakdown, calculatePrice } from './pricing';
import { LegacyLandingPage } from './legacy/LandingPage.legacy';
import type { LandingContent } from './types';

let authenticated = false;
vi.mock('../../../hooks/useAuth', () => ({ useAuth: () => ({ isAuthenticated: authenticated }) }));

class NoopObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopObserver);
  if (!window.matchMedia) {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
    }));
  }
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderBoth(isAuth = false) {
  authenticated = isAuth;
  const legacy = render(<MemoryRouter><LegacyLandingPage /></MemoryRouter>);
  const current = render(<MemoryRouter><LandingView content={DEFAULT_LANDING_CONTENT} isAuthenticated={isAuth} /></MemoryRouter>);
  return { legacy: legacy.container, current: current.container };
}

const html = (el: HTMLElement) => el.innerHTML;

describe('CMS migration keeps the public landing page identical', () => {
  it('seeded content validates', () => {
    expect(isLandingContent(DEFAULT_LANDING_CONTENT)).toBe(true);
  });

  it('renders byte-identical HTML to the original page (signed out and signed in)', () => {
    for (const isAuth of [false, true]) {
      const { legacy, current } = renderBoth(isAuth);
      expect(html(current)).toBe(html(legacy));
      legacy.remove();
      current.remove();
    }
  });

  it('stays identical through every pricing model and quantity', () => {
    const { legacy, current } = renderBoth();
    const cards = (root: HTMLElement) =>
      Array.from(root.querySelector('#pricing-models .grid')!.children) as HTMLElement[];
    expect(cards(current)).toHaveLength(5);
    for (let model = 0; model < 5; model++) {
      fireEvent.click(cards(legacy)[model]);
      fireEvent.click(cards(current)[model]);
      for (const qty of ['1', '50', '51', '150', '151', '200', '201', '333', '500']) {
        const sliders = [legacy, current].map((root) => root.querySelector('input[type=range]') as HTMLInputElement | null);
        if (sliders[0] && sliders[1]) {
          fireEvent.change(sliders[0], { target: { value: qty } });
          fireEvent.change(sliders[1], { target: { value: qty } });
        }
        act(() => {
          vi.advanceTimersByTime(10);
        });
        expect(html(current)).toBe(html(legacy));
      }
    }
  });

  it('stays identical through the FAQ and every workflow stage', () => {
    const { legacy, current } = renderBoth();
    const faqButtons = (root: HTMLElement) => Array.from(root.querySelectorAll('#faq button')) as HTMLElement[];
    for (let i = 0; i < 5; i++) {
      fireEvent.click(faqButtons(legacy)[i]);
      fireEvent.click(faqButtons(current)[i]);
      expect(html(current)).toBe(html(legacy));
    }
    const stages = (root: HTMLElement) =>
      Array.from(root.querySelectorAll('#workflow .min-w-\\[800px\\] > button')) as HTMLElement[];
    expect(stages(current)).toHaveLength(9);
    for (let i = 0; i < 9; i++) {
      fireEvent.click(stages(legacy)[i]);
      fireEvent.click(stages(current)[i]);
      expect(html(current)).toBe(html(legacy));
    }
    act(() => {
      vi.advanceTimersByTime(4300); // one auto-tour step on both
    });
    expect(html(current)).toBe(html(legacy));
  });
});

// Reference implementation copied verbatim from the original page (the pre-CMS pricingModels and
// currentBreakdown), used to prove the parameterised calculator is exact for every quantity.
function legacyCalculate(model: number, qty: number): number {
  switch (model) {
    case 0: return 299;
    case 1: return qty * 15;
    case 2: { const rate = qty > 200 ? 10 : qty > 50 ? 14 : 20; return qty * rate; }
    case 3: {
      let total = 0;
      total += Math.min(qty, 50) * 20;
      if (qty > 50) total += Math.min(qty - 50, 100) * 12;
      if (qty > 150) total += (qty - 150) * 8;
      return total;
    }
    default: return Math.ceil(qty / 50) * 450;
  }
}

describe('illustrative pricing calculator', () => {
  const models = DEFAULT_LANDING_CONTENT.pricing.models;

  it('matches the original arithmetic for every quantity 1..500', () => {
    for (let m = 0; m < 5; m++) {
      for (let qty = 1; qty <= 500; qty++) {
        expect(calculatePrice(models[m], qty)).toBe(legacyCalculate(m, qty));
        expect(buildBreakdown(models[m], qty).finalPrice).toBe(legacyCalculate(m, qty));
      }
    }
  });

  it('recalculates from edited example values without code changes', () => {
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.pricing.models[0].price = 499;
    edited.pricing.models[1].price = 20;
    edited.pricing.models[4].bundle_size = 25;
    edited.pricing.models[4].price = 300;
    expect(calculatePrice(edited.pricing.models[0], 10)).toBe(499);
    expect(buildBreakdown(edited.pricing.models[0], 1).formula).toBe('Fixed Platform Rate = ₹499.00 / month');
    expect(calculatePrice(edited.pricing.models[1], 10)).toBe(200);
    expect(buildBreakdown(edited.pricing.models[4], 60).quantity).toBe('3 bundles');
    expect(calculatePrice(edited.pricing.models[4], 60)).toBe(900);
  });
});

describe('content controls', () => {
  it('hides invisible sections and items, reorders sections, and keeps links safe', () => {
    authenticated = false;
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.faq.visible = false;
    edited.hero.visible = false;
    edited.operations.cards[0].visible = false;
    edited.section_order = ['final_cta', ...edited.section_order.filter((k) => k !== 'final_cta')];
    edited.footer.columns[0].links[0] = { label: 'Docs', link: 'https://docs.example.com/start' };
    const { container } = render(<MemoryRouter><LandingView content={edited} isAuthenticated={false} /></MemoryRouter>);
    expect(container.querySelector('#faq')).toBeNull();
    expect(container.textContent).not.toContain('Powerful billing.');
    expect(container.textContent).not.toContain('Centralized inbox for pending invoices');
    const sections = Array.from(container.querySelectorAll('section'));
    expect(sections[0].textContent).toContain('Ready to simplify your billing?');
    const external = Array.from(container.querySelectorAll('a')).find((a) => a.textContent === 'Docs')!;
    expect(external.getAttribute('href')).toBe('https://docs.example.com/start');
    expect(external.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders markup-looking text as text, never as HTML', () => {
    const edited: LandingContent = JSON.parse(JSON.stringify(DEFAULT_LANDING_CONTENT));
    edited.hero.headline = '<img src=x onerror=alert(1)>';
    const { container } = render(<MemoryRouter><LandingView content={edited} isAuthenticated={false} /></MemoryRouter>);
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
