import axios, { AxiosError, AxiosInstance } from 'axios';
import { API_BASE_URL, toApiError } from './apiClient';
import { triggerBlobDownload } from './download';
import type {
  PortalLoginIn,
  PortalSignupIn,
  PortalAuthOut,
  PortalUserOut,
  PortalActivateIn,
  PortalInvitationValidateOut,
} from '../types/portal';

export interface PortalDashboardData {
  /** Set when the merchant is suspended: the portal is read-only. */
  read_only_reason?: string | null;
  customer_name: string;
  customer_email: string | null;
  active_subscriptions_count: number;
  open_invoices_count: number;
  total_outstanding_amount: number | string;
  recent_invoices: Array<{
    id: string;
    invoice_number: string;
    issue_date: string;
    due_date: string;
    total: string;
    amount_due: string;
    status: string;
    public_token: string;
  }>;
  subscriptions: Array<{
    id: string;
    subscription_number: string;
    plan_name: string;
    status: string;
    current_period_end: string;
    trial_end: string | null;
  }>;
  saved_payment_methods: Array<{
    id: string;
    type: string;
    card_brand?: string;
    last4?: string;
    is_default: boolean;
  }>;
}

export interface PortalInvoice {
  id: string;
  invoice_number: string;
  issue_date: string;
  due_date: string;
  total: string;
  amount_paid: string;
  amount_due: string;
  status: string;
  public_token: string;
}

export interface PortalInvoiceItem {
  id: string;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
  tax_rate_pct: number;
  hsn_sac_code?: string;
}

export interface PortalInvoiceDetail extends PortalInvoice {
  currency: string;
  subtotal: string;
  tax_amount: string;
  notes?: string;
  terms?: string;
  place_of_supply_name?: string;
  customer_gstin?: string;
  items: PortalInvoiceItem[];
}

export interface PortalPayment {
  id: string;
  payment_number: string;
  amount: string;
  currency: string;
  method: string;
  gateway: string;
  status: string;
  reconciliation_status: string;
  created_at: string;
  gateway_payment_id?: string;
}

export interface PortalSubscription {
  id: string;
  subscription_number: string;
  plan_name: string;
  quantity: number;
  status: string;
  current_period_start: string;
  current_period_end: string;
  trial_end: string | null;
}

export interface PortalProfileData {
  user: {
    id: string;
    email: string;
    display_name: string;
  };
  customer: {
    id: string;
    customer_number: string;
    display_name: string;
    company_name?: string;
    email?: string;
    phone?: string;
    website?: string;
    gstin?: string;
    pan?: string;
    currency: string;
    billing_address_line1?: string;
    billing_address_line2?: string;
    billing_city?: string;
    billing_state?: string;
    billing_postal_code?: string;
    billing_country?: string;
  };
  contacts: Array<{
    id: string;
    name: string;
    email?: string;
    phone?: string;
    designation?: string;
    is_primary: boolean;
  }>;
}

const PORTAL_TOKEN_KEY = 'rooman.portal_token';
const PORTAL_USER_KEY = 'rooman.portal_user';
const PORTAL_CUSTOMER_NAME_KEY = 'rooman.portal_customer_name';

export const portalTokenStorage = {
  getToken: (): string | null => {
    try {
      return window.localStorage.getItem(PORTAL_TOKEN_KEY);
    } catch {
      return null;
    }
  },
  setSession: (auth: PortalAuthOut): void => {
    try {
      window.localStorage.setItem(PORTAL_TOKEN_KEY, auth.token);
      window.localStorage.setItem(PORTAL_USER_KEY, JSON.stringify(auth.user));
      window.localStorage.setItem(PORTAL_CUSTOMER_NAME_KEY, auth.customer_display_name || '');
    } catch {
      // ignore storage error
    }
  },
  getUser: (): PortalUserOut | null => {
    try {
      const raw = window.localStorage.getItem(PORTAL_USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  getCustomerName: (): string => {
    try {
      return window.localStorage.getItem(PORTAL_CUSTOMER_NAME_KEY) || '';
    } catch {
      return '';
    }
  },
  clear: (): void => {
    try {
      window.localStorage.removeItem(PORTAL_TOKEN_KEY);
      window.localStorage.removeItem(PORTAL_USER_KEY);
      window.localStorage.removeItem(PORTAL_CUSTOMER_NAME_KEY);
    } catch {
      // ignore
    }
  },
  hasSession: (): boolean => Boolean(portalTokenStorage.getToken()),
};

const portalClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/portal`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 20000,
});

portalClient.interceptors.request.use((config) => {
  const token = portalTokenStorage.getToken();
  if (token) {
    config.headers['X-Portal-Token'] = token;
  }
  return config;
});

/** Dispatched on `window` when the portal session has expired or been revoked. */
export const PORTAL_LOGOUT_EVENT = 'rooman:portal-logout';

function isPortalAuthRoute(url: string | undefined): boolean {
  return Boolean(url && /(^|\/)auth\//.test(url));
}

/** Clears the portal session and sends the customer back to the portal login. */
function handlePortalSessionExpired(): void {
  portalTokenStorage.clear();
  try {
    window.dispatchEvent(new CustomEvent(PORTAL_LOGOUT_EVENT));
    if (!window.location.pathname.startsWith('/portal/login')) {
      window.location.assign('/portal/login?expired=1');
    }
  } catch {
    // no window (tests) - nothing to redirect
  }
}

// Normalise every failure to an ApiError ({ code, message, status }) using the
// backend envelope `{ error: { message } }`, same as the staff apiClient, so
// pages can simply show `err.message`.
portalClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status;
    if (status === 401 && !isPortalAuthRoute(error.config?.url) && portalTokenStorage.hasSession()) {
      handlePortalSessionExpired();
    }
    return Promise.reject(toApiError(error));
  }
);

export interface PortalSavedPaymentMethod {
  id: string;
  type: string;
  card_brand?: string;
  last4?: string;
  is_default: boolean;
}

export interface PortalProfileUpdate {
  display_name?: string;
  email?: string;
  phone?: string;
  website?: string;
  billing_address_line1?: string;
  billing_address_line2?: string;
  billing_city?: string;
  billing_state?: string;
  billing_postal_code?: string;
  billing_country?: string;
  shipping_address_line1?: string;
  shipping_address_line2?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
  user_display_name?: string;
}

export const portalCustomerService = {
  login: async (credentials: PortalLoginIn): Promise<PortalAuthOut> => {
    const { data } = await portalClient.post<PortalAuthOut>('/auth/login', credentials);
    portalTokenStorage.setSession(data);
    return data;
  },

  validateInvitation: async (token: string): Promise<PortalInvitationValidateOut> => {
    const { data } = await portalClient.get<PortalInvitationValidateOut>('/auth/invitation', {
      params: { token },
    });
    return data;
  },

  activate: async (payload: PortalActivateIn): Promise<PortalAuthOut> => {
    const { data } = await portalClient.post<PortalAuthOut>('/auth/activate', payload);
    portalTokenStorage.setSession(data);
    return data;
  },

  signup: async (signupData: PortalSignupIn): Promise<PortalUserOut> => {
    const { data } = await portalClient.post<PortalUserOut>('/auth/signup', signupData);
    return data;
  },

  logout: async (): Promise<void> => {
    try {
      await portalClient.post('/auth/logout');
    } catch {
      // Ignore network errors on logout
    } finally {
      portalTokenStorage.clear();
    }
  },

  getDashboard: async (): Promise<PortalDashboardData> => {
    const { data } = await portalClient.get<PortalDashboardData>('/dashboard');
    return data;
  },

  getInvoices: async (): Promise<PortalInvoice[]> => {
    const { data } = await portalClient.get<PortalInvoice[]>('/invoices');
    return data;
  },

  getInvoice: async (invoiceId: string): Promise<PortalInvoiceDetail> => {
    const { data } = await portalClient.get<PortalInvoiceDetail>(`/invoices/${invoiceId}`);
    return data;
  },

  downloadInvoicePdf: async (invoiceId: string, invoiceNumber: string): Promise<void> => {
    const token = portalTokenStorage.getToken();
    const headers: Record<string, string> = {};
    if (token) headers['X-Portal-Token'] = token;

    const response = await fetch(`${API_BASE_URL}/portal/invoices/${invoiceId}/pdf`, {
      headers,
      credentials: 'omit',
    });

    if (!response.ok) {
      if (response.status === 401 && portalTokenStorage.hasSession()) handlePortalSessionExpired();
      throw new Error(`Failed to download invoice PDF (${response.status})`);
    }

    const blob = await response.blob();
    triggerBlobDownload(blob, `${invoiceNumber}.pdf`);
  },

  getPayments: async (): Promise<PortalPayment[]> => {
    const { data } = await portalClient.get<PortalPayment[]>('/payments');
    return data;
  },

  getSubscriptions: async (): Promise<PortalSubscription[]> => {
    const { data } = await portalClient.get<PortalSubscription[]>('/subscriptions');
    return data;
  },

  getProfile: async (): Promise<PortalProfileData> => {
    const { data } = await portalClient.get<PortalProfileData>('/profile');
    return data;
  },

  updateProfile: async (payload: PortalProfileUpdate): Promise<PortalProfileData> => {
    const { data } = await portalClient.patch<PortalProfileData>('/profile', payload);
    return data;
  },

  getPaymentMethods: async (): Promise<PortalSavedPaymentMethod[]> => {
    const { data } = await portalClient.get<PortalSavedPaymentMethod[]>('/payment-methods');
    return data;
  },

  setDefaultPaymentMethod: async (methodId: string): Promise<void> => {
    await portalClient.patch(`/payment-methods/${methodId}/default`);
  },

  deletePaymentMethod: async (methodId: string): Promise<void> => {
    await portalClient.delete(`/payment-methods/${methodId}`);
  },
};
