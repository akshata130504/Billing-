import { useQuery } from '@tanstack/react-query';
import { platformSubscriptionService, type PublicPlanCatalog } from '../services/platformSubscriptionService';

export const PUBLIC_PLANS_QUERY_KEY = ['public-plans'] as const;

/** The published Rooman plan catalog (GET /public/plans), shared by the subscription page and the banner. */
export function usePublicPlans(enabled = true) {
  return useQuery({ queryKey: PUBLIC_PLANS_QUERY_KEY, queryFn: platformSubscriptionService.listPlans, enabled });
}

export const SANDBOX_PLANS_QUERY_KEY = ['sandbox-plans'] as const;

/**
 * Sandbox TEST plans for a Razorpay Test Mode purchase: empty unless the server allows the sandbox. Kept apart
 * from the public catalog on purpose - nothing that advertises plans (banner, "View Plans") ever counts them.
 */
export function useSandboxPlans() {
  return useQuery({ queryKey: SANDBOX_PLANS_QUERY_KEY, queryFn: platformSubscriptionService.listSandboxPlans, retry: false });
}

/**
 * At least one plan can be bought right now (published, and the server says checkout is ready). Until then
 * nothing should invite the user to choose a plan. Unknown (loading or failed) counts as no.
 */
export function hasPurchasablePlan(catalog: PublicPlanCatalog | null | undefined): boolean {
  return !!catalog?.plans.some((plan) => plan.purchasable && !plan.sandbox); // a test plan is never an offer
}
