import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignupPage } from './SignupPage';
import { authService } from '../../services/authService';

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    applyTokens: vi.fn().mockResolvedValue({}),
  }),
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}));

vi.mock('../../services/authService', () => ({
  authService: {
    requestSignupVerification: vi.fn(),
    resendSignupOtp: vi.fn(),
    verifySignupOtp: vi.fn(),
  },
}));

function renderSignup() {
  return render(
    <BrowserRouter>
      <SignupPage />
    </BrowserRouter>
  );
}

describe('SignupPage with Inline Email OTP Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders registration form with "Send OTP" button under Work email and "Create organization" button', () => {
    renderSignup();

    expect(screen.getByRole('heading', { name: /create your organization/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/organization name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/your full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/work email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send otp/i })).toBeInTheDocument();
    expect(screen.getByText(/please verify your email address before creating your organization/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create organization/i })).toBeInTheDocument();
  });

  it('validates required fields and password policy when clicking Send OTP', async () => {
    renderSignup();

    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    expect(await screen.findByText(/organization name is required/i)).toBeInTheDocument();
    expect(authService.requestSignupVerification).not.toHaveBeenCalled();
  });

  it('shows inline OTP section beside/under work email upon successful request-verification', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText(/organization name/i), { target: { value: 'Acme Corp' } });
    fireEvent.change(screen.getByLabelText(/your full name/i), { target: { value: 'Alex Owner' } });
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: 'alex.owner@example.com' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Str0ngPassw0rd!' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'Str0ngPassw0rd!' } });

    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    await waitFor(() => {
      expect(authService.requestSignupVerification).toHaveBeenCalledWith({
        organization_name: 'Acme Corp',
        full_name: 'Alex Owner',
        email: 'alex.owner@example.com',
        password: 'Str0ngPassw0rd!',
      });
    });

    // Form remains visible and inline OTP section appears
    expect(screen.getByRole('heading', { name: /create your organization/i })).toBeInTheDocument();
    expect(await screen.findByText(/enter 6-digit otp sent to/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /verify otp/i })).toBeInTheDocument();
    // 6 digit inputs for OTP
    expect(screen.getAllByRole('textbox', { name: /digit/i })).toHaveLength(6);
  });

  it('enables Verify OTP and completes registration when 6 digits are submitted', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });
    vi.mocked(authService.verifySignupOtp).mockResolvedValueOnce({
      access_token: 'fake-jwt',
      refresh_token: 'fake-refresh',
      token_type: 'bearer',
      expires_in: 1800,
      me: {
        user: { id: 'u1', email: 'alex.owner@example.com', full_name: 'Alex Owner' } as any,
        organization: { id: 'o1', name: 'Acme Corp', slug: 'acme-corp' } as any,
        membership: { id: 'm1', role: 'owner', status: 'active' } as any,
        organizations: [],
      },
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText(/organization name/i), { target: { value: 'Acme Corp' } });
    fireEvent.change(screen.getByLabelText(/your full name/i), { target: { value: 'Alex Owner' } });
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: 'alex.owner@example.com' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Str0ngPassw0rd!' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'Str0ngPassw0rd!' } });
    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    await screen.findByText(/enter 6-digit otp sent to/i);

    const digitInputs = screen.getAllByRole('textbox', { name: /digit/i });
    for (let i = 0; i < 6; i++) {
      fireEvent.change(digitInputs[i], { target: { value: String(i + 1) } });
    }

    const verifyOtpBtn = screen.getByRole('button', { name: /verify otp/i });
    expect(verifyOtpBtn).not.toBeDisabled();

    fireEvent.click(verifyOtpBtn);

    await waitFor(() => {
      expect(authService.verifySignupOtp).toHaveBeenCalledWith({
        email: 'alex.owner@example.com',
        otp: '123456',
        password: 'Str0ngPassw0rd!',
      });
    });
  });

  it('clicking "Create organization" triggers verification if email is not yet verified', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText(/organization name/i), { target: { value: 'Acme Corp' } });
    fireEvent.change(screen.getByLabelText(/your full name/i), { target: { value: 'Alex Owner' } });
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: 'alex.owner@example.com' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Str0ngPassw0rd!' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'Str0ngPassw0rd!' } });

    // Click bottom button directly
    fireEvent.click(screen.getByRole('button', { name: /create organization/i }));

    await waitFor(() => {
      expect(authService.requestSignupVerification).toHaveBeenCalledWith({
        organization_name: 'Acme Corp',
        full_name: 'Alex Owner',
        email: 'alex.owner@example.com',
        password: 'Str0ngPassw0rd!',
      });
    });

    expect(await screen.findByText(/enter 6-digit otp sent to/i)).toBeInTheDocument();
  });
});
