import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Badge } from './Badge';
import { statusVariant } from '../../utils/format';

describe('<Badge />', () => {
  it('renders its children', () => {
    render(<Badge>Overdue</Badge>);
    expect(screen.getByText('Overdue')).toBeInTheDocument();
  });

  it('defaults to the neutral variant', () => {
    render(<Badge>Draft</Badge>);
    const badge = screen.getByText('Draft').parentElement!;
    expect(badge.className).toContain('bg-slate-100');
    expect(badge.className).toContain('text-slate-700');
  });

  it('applies the colour scheme for each variant', () => {
    const cases: Array<[Parameters<typeof Badge>[0]['variant'], string]> = [
      ['success', 'bg-emerald-50'],
      ['danger', 'bg-rose-50'],
      ['warning', 'bg-amber-50'],
      ['info', 'bg-sky-50'],
      ['primary', 'bg-blue-50'],
    ];
    for (const [variant, expected] of cases) {
      const { unmount } = render(<Badge variant={variant}>{variant}</Badge>);
      expect(screen.getByText(String(variant)).parentElement!.className).toContain(expected);
      unmount();
    }
  });

  it('renders a decorative dot only when asked, hidden from screen readers', () => {
    const { container, rerender } = render(<Badge variant="danger">Overdue</Badge>);
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();

    rerender(
      <Badge variant="danger" dot>
        Overdue
      </Badge>
    );
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).not.toBeNull();
    expect(dot!.className).toContain('bg-rose-500');
  });

  it('supports the small size', () => {
    render(<Badge size="sm">Paid</Badge>);
    expect(screen.getByText('Paid').parentElement!.className).toContain('text-[11px]');
  });

  it('merges a caller className and forwards span attributes', () => {
    render(
      <Badge className="ml-2" title="Invoice status" data-testid="status-badge">
        Paid
      </Badge>
    );
    const badge = screen.getByTestId('status-badge');
    expect(badge.className).toContain('ml-2');
    expect(badge).toHaveAttribute('title', 'Invoice status');
  });

  it('renders the variant statusVariant() picks for a real invoice status', () => {
    render(<Badge variant={statusVariant('overdue')}>Overdue</Badge>);
    expect(screen.getByText('Overdue').parentElement!.className).toContain('bg-rose-50');
  });
});
