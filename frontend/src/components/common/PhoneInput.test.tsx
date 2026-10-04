import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PhoneInput } from './PhoneInput';

function Harness({ onSpy, initial = '' }: { onSpy: (v: string) => void; initial?: string }) {
  const [v, setV] = useState(initial);
  return (
    <PhoneInput
      label="Phone"
      value={v}
      onChange={(x) => {
        setV(x);
        onSpy(x);
      }}
    />
  );
}

describe('PhoneInput', () => {
  it('makes the library root fill the bordered wrapper', () => {
    const { container } = render(<PhoneInput label="Phone" onChange={() => {}} />);
    const root = container.querySelector('.PhoneInput') as HTMLElement;
    expect(root).toHaveClass('w-full');
    expect(root).toHaveClass('h-full');
    expect(root.parentElement).toHaveClass('rooman-phone-input', 'h-[38px]');
  });

  it('associates the label with the input', () => {
    render(<PhoneInput label="Phone" onChange={() => {}} />);
    const input = screen.getByLabelText('Phone');
    expect(input.tagName).toBe('INPUT');
  });

  it('emits E.164 with the default country IN', () => {
    const spy = vi.fn();
    render(<Harness onSpy={spy} />);
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '+919876543210' } });
    expect(spy).toHaveBeenLastCalledWith('+919876543210');
  });

  it('shows the error message and a rose border', () => {
    const { container } = render(<PhoneInput label="Phone" error="Invalid phone" onChange={() => {}} />);
    expect(screen.getByText('Invalid phone')).toBeInTheDocument();
    expect(container.querySelector('.rooman-phone-input')).toHaveClass('border-rose-300');
  });

  it('disables the input', () => {
    render(<PhoneInput label="Phone" disabled onChange={() => {}} />);
    expect(screen.getByLabelText('Phone')).toBeDisabled();
  });

  it('renders an initial E.164 value formatted', () => {
    render(<PhoneInput label="Phone" value="+919876543210" onChange={() => {}} />);
    expect((screen.getByLabelText('Phone') as HTMLInputElement).value).toBe('+91 98765 43210');
  });

  it('emits an empty string when cleared', () => {
    const spy = vi.fn();
    render(<Harness onSpy={spy} initial="+919876543210" />);
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '' } });
    expect(spy).toHaveBeenLastCalledWith('');
  });
});
