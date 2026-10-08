import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignupPage } from './SignupPage';
import { authService } from '../../services/authService';

const { applyTokens } = vi.hoisted(() => ({ applyTokens: vi.fn() }));

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    applyTokens,
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
    confirmSignupEmail: vi.fn(),
    completeSignup: vi.fn(),
    verifySignupOtp: vi.fn(),
  },
}));

const VALID_PASSWORD = 'Str0ngPassw0rd!';
const PASSWORD_MESSAGE = /password does not meet the requirements below/i;

const signupResponse = {
  access_token: 'fake-jwt',
  refresh_token: 'fake-refresh',
  token_type: 'bearer' as const,
  expires_in: 1800,
  me: {
    user: { id: 'u1', email: 'alex.owner@example.com', full_name: 'Alex Owner' } as any,
    organization: { id: 'o1', name: 'Acme Corp', slug: 'acme-corp' } as any,
    membership: { id: 'm1', role: 'owner', status: 'active' } as any,
    organizations: [],
  },
};

function renderSignup() {
  return render(
    <BrowserRouter>
      <SignupPage />
    </BrowserRouter>
  );
}

function fillDetails(email = 'alex.owner@example.com') {
  fireEvent.change(screen.getByLabelText(/organization name/i), { target: { value: 'Acme Corp' } });
  fireEvent.change(screen.getByLabelText(/your full name/i), { target: { value: 'Alex Owner' } });
  fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: email } });
}

async function sendOtp() {
  fireEvent.click(screen.getByRole('button', { name: /send otp/i }));
  await screen.findByText(/enter 6-digit otp sent to/i);
}

function enterCode(code = '123456') {
  const digitInputs = screen.getAllByRole('textbox', { name: /digit/i });
  for (let i = 0; i < 6; i++) {
    fireEvent.change(digitInputs[i], { target: { value: code[i] } });
  }
}

/** Fills the details, sends the code and verifies it, ending on the "choose a password" step. */
async function reachPasswordStep() {
  vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
    message: 'Code sent',
    email: 'alex.owner@example.com',
    expires_in_seconds: 600,
    resend_cooldown_seconds: 60,
  });
  vi.mocked(authService.confirmSignupEmail).mockResolvedValueOnce({
    verification_token: 'proof-of-email',
    expires_in_seconds: 900,
  });
  renderSignup();
  fillDetails();
  await sendOtp();
  enterCode();
  fireEvent.click(screen.getByRole('button', { name: /verify otp/i }));
  await screen.findByLabelText(/^password/i);
}

const passwordInput = () => screen.getByLabelText(/^password/i) as HTMLInputElement;
const confirmInput = () => screen.getByLabelText(/confirm password/i) as HTMLInputElement;
const requirement = (label: RegExp) => screen.getByText(label).closest('li') as HTMLElement;
const isMet = (li: HTMLElement) => li.className.includes('emerald');

describe('SignupPage: email OTP first, password after verification', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    applyTokens.mockResolvedValue({});
  });

  it('renders the details form with Send OTP, a disabled Create organization and no password fields yet', () => {
    renderSignup();

    expect(screen.getByRole('heading', { name: /create your organization/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/organization name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/your full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/work email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send otp/i })).toBeInTheDocument();
    expect(screen.getByText(/please verify your email address before creating your organization/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create organization/i })).toBeDisabled();
    // The password is chosen only after the email is verified.
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/confirm password/i)).not.toBeInTheDocument();
    expect(screen.queryByText(PASSWORD_MESSAGE)).not.toBeInTheDocument();
  });

  it('validates the required details when clicking Send OTP', async () => {
    renderSignup();

    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    expect(await screen.findByText(/organization name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/full name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/work email is required/i)).toBeInTheDocument();
    // Never a password complaint: it is not part of this step.
    expect(screen.queryByText(PASSWORD_MESSAGE)).not.toBeInTheDocument();
    expect(authService.requestSignupVerification).not.toHaveBeenCalled();
  });

  it('does not request an OTP for an invalid email', async () => {
    renderSignup();
    fillDetails('not-an-email');

    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    expect(await screen.findByText(/valid work email/i)).toBeInTheDocument();
    expect(authService.requestSignupVerification).not.toHaveBeenCalled();
  });

  it('requests the OTP with only the organization details and email, no password', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });
    renderSignup();
    fillDetails();

    fireEvent.click(screen.getByRole('button', { name: /send otp/i }));

    await waitFor(() => {
      expect(authService.requestSignupVerification).toHaveBeenCalledWith({
        organization_name: 'Acme Corp',
        full_name: 'Alex Owner',
        email: 'alex.owner@example.com',
      });
    });
    expect(await screen.findByText(/enter 6-digit otp sent to/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /verify otp/i })).toBeInTheDocument();
    expect(screen.getAllByRole('textbox', { name: /digit/i })).toHaveLength(6);
    // Still no password step, and still nothing can be created.
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create organization/i })).toBeDisabled();
  });

  it('sends the OTP when Enter is pressed in the email field', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });
    renderSignup();
    fillDetails();

    fireEvent.keyDown(screen.getByLabelText(/work email/i), { key: 'Enter' });

    await waitFor(() => expect(authService.requestSignupVerification).toHaveBeenCalledTimes(1));
  });

  it('verifies the code without creating anything, then reveals the password step', async () => {
    await reachPasswordStep();

    expect(authService.confirmSignupEmail).toHaveBeenCalledWith({ email: 'alex.owner@example.com', otp: '123456' });
    expect(authService.completeSignup).not.toHaveBeenCalled();
    expect(authService.verifySignupOtp).not.toHaveBeenCalled();
    expect(applyTokens).not.toHaveBeenCalled();
    expect(screen.getByText(/work email verified successfully/i)).toBeInTheDocument();
    expect(passwordInput()).toBeInTheDocument();
    expect(confirmInput()).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create organization/i })).not.toBeDisabled();
  });

  it('does not show a password error before the user has interacted with the password field', async () => {
    await reachPasswordStep();

    expect(screen.queryByText(PASSWORD_MESSAGE)).not.toBeInTheDocument();
    // The guidance itself is there from the start, all unmet.
    expect(isMet(requirement(/at least 10 characters/i))).toBe(false);
    expect(isMet(requirement(/upper and lower case letters/i))).toBe(false);
    expect(isMet(requirement(/at least one digit/i))).toBe(false);
  });

  it('shows the password error for an invalid password and removes it as soon as the password is valid', async () => {
    await reachPasswordStep();

    fireEvent.change(passwordInput(), { target: { value: 'short' } });
    fireEvent.blur(passwordInput());
    expect(screen.getByText(PASSWORD_MESSAGE)).toBeInTheDocument();

    // Still invalid while typing: the message stays...
    fireEvent.change(passwordInput(), { target: { value: 'Str0ngPas' } });
    expect(screen.getByText(PASSWORD_MESSAGE)).toBeInTheDocument();

    // ...and goes the moment every requirement is met, with no submit or blur needed.
    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    expect(screen.queryByText(PASSWORD_MESSAGE)).not.toBeInTheDocument();

    // Back to invalid: it returns.
    fireEvent.change(passwordInput(), { target: { value: 'weak' } });
    expect(screen.getByText(PASSWORD_MESSAGE)).toBeInTheDocument();
  });

  it('updates each requirement indicator as the password changes', async () => {
    await reachPasswordStep();
    const length = () => isMet(requirement(/at least 10 characters/i));
    const mixedCase = () => isMet(requirement(/upper and lower case letters/i));
    const digit = () => isMet(requirement(/at least one digit/i));

    fireEvent.change(passwordInput(), { target: { value: 'abcdefghijkl' } });
    expect([length(), mixedCase(), digit()]).toEqual([true, false, false]);

    fireEvent.change(passwordInput(), { target: { value: 'Abc1' } });
    expect([length(), mixedCase(), digit()]).toEqual([false, true, true]);

    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    expect([length(), mixedCase(), digit()]).toEqual([true, true, true]);

    fireEvent.change(passwordInput(), { target: { value: '' } });
    expect([length(), mixedCase(), digit()]).toEqual([false, false, false]);
  });

  it('shows the mismatch error live and clears it when the passwords match', async () => {
    await reachPasswordStep();

    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    fireEvent.change(confirmInput(), { target: { value: 'Different1Passw0rd' } });
    fireEvent.blur(confirmInput());
    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();

    fireEvent.change(confirmInput(), { target: { value: VALID_PASSWORD } });
    expect(screen.queryByText(/passwords do not match/i)).not.toBeInTheDocument();
  });

  it('refuses to create the organization with an invalid password', async () => {
    await reachPasswordStep();
    fireEvent.change(passwordInput(), { target: { value: 'weakpass' } });
    fireEvent.change(confirmInput(), { target: { value: 'weakpass' } });

    fireEvent.click(screen.getByRole('button', { name: /create organization/i }));

    expect(await screen.findByText(PASSWORD_MESSAGE)).toBeInTheDocument();
    expect(authService.completeSignup).not.toHaveBeenCalled();
  });

  it('refuses to create the organization when the confirmation does not match', async () => {
    await reachPasswordStep();
    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    fireEvent.change(confirmInput(), { target: { value: `${VALID_PASSWORD}x` } });

    fireEvent.click(screen.getByRole('button', { name: /create organization/i }));

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
    expect(authService.completeSignup).not.toHaveBeenCalled();
  });

  it('cannot create the organization before the email is verified', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });
    renderSignup();
    fillDetails();
    await sendOtp();

    const create = screen.getByRole('button', { name: /create organization/i });
    expect(create).toBeDisabled();
    fireEvent.click(create);
    fireEvent.submit(create.closest('form') as HTMLFormElement);

    expect(authService.completeSignup).not.toHaveBeenCalled();
    expect(applyTokens).not.toHaveBeenCalled();
  });

  it('creates the organization with the verification token and the chosen password', async () => {
    vi.mocked(authService.completeSignup).mockResolvedValueOnce(signupResponse);
    await reachPasswordStep();

    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    fireEvent.change(confirmInput(), { target: { value: VALID_PASSWORD } });
    fireEvent.click(screen.getByRole('button', { name: /create organization/i }));

    await waitFor(() => {
      expect(authService.completeSignup).toHaveBeenCalledWith({
        email: 'alex.owner@example.com',
        verification_token: 'proof-of-email',
        organization_name: 'Acme Corp',
        full_name: 'Alex Owner',
        password: VALID_PASSWORD,
      });
    });
    await waitFor(() => expect(applyTokens).toHaveBeenCalledWith(signupResponse));
  });

  it('asks for the email to be verified again when the verification has expired', async () => {
    vi.mocked(authService.completeSignup).mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Your email verification has expired or is invalid. Please verify your email again.',
            details: { fields: { verification_token: 'invalid' } },
          },
        },
      },
      isAxiosError: true,
    });
    await reachPasswordStep();
    fireEvent.change(passwordInput(), { target: { value: VALID_PASSWORD } });
    fireEvent.change(confirmInput(), { target: { value: VALID_PASSWORD } });

    fireEvent.click(screen.getByRole('button', { name: /create organization/i }));

    await waitFor(() => expect(authService.completeSignup).toHaveBeenCalled());
    expect(await screen.findByText(/verify your email address before creating your organization/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create organization/i })).toBeDisabled();
    expect(applyTokens).not.toHaveBeenCalled();
  });

  it('keeps the email verification step working: a wrong code shows the server message', async () => {
    vi.mocked(authService.requestSignupVerification).mockResolvedValueOnce({
      message: 'Code sent',
      email: 'alex.owner@example.com',
      expires_in_seconds: 600,
      resend_cooldown_seconds: 60,
    });
    vi.mocked(authService.confirmSignupEmail).mockRejectedValueOnce({
      response: {
        status: 422,
        data: { error: { code: 'VALIDATION_ERROR', message: 'Invalid verification code. 4 attempt(s) remaining.', details: {} } },
      },
      isAxiosError: true,
    });
    renderSignup();
    fillDetails();
    await sendOtp();
    enterCode('000000');

    fireEvent.click(screen.getByRole('button', { name: /verify otp/i }));

    expect(await screen.findByText(/invalid verification code/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    expect(authService.completeSignup).not.toHaveBeenCalled();
  });
});
