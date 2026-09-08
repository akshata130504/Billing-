import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EmptyState } from './EmptyState';

describe('<EmptyState />', () => {
  it('renders the title as a heading plus the description', () => {
    render(<EmptyState title="No payments yet" description="Record a payment to see it here." />);
    expect(screen.getByRole('heading', { name: 'No payments yet' })).toBeInTheDocument();
    expect(screen.getByText('Record a payment to see it here.')).toBeInTheDocument();
  });

  it('falls back to a default icon so the state never looks broken', () => {
    const { container } = render(<EmptyState title="Nothing here" description="…" />);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('uses a supplied icon instead of the default', () => {
    render(
      <EmptyState title="Nothing here" description="…" icon={<span data-testid="custom-icon">!</span>} />
    );
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('renders no action area unless an action is given', () => {
    render(<EmptyState title="No invoices" description="…" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders the action when supplied', () => {
    render(
      <EmptyState title="No invoices" description="…" action={<button type="button">New invoice</button>} />
    );
    expect(screen.getByRole('button', { name: 'New invoice' })).toBeInTheDocument();
  });

  it('merges a caller className onto the wrapper', () => {
    const { container } = render(<EmptyState title="t" description="d" className="mt-8" />);
    expect(container.firstElementChild!.className).toContain('mt-8');
    expect(container.firstElementChild!.className).toContain('border-dashed');
  });
});
