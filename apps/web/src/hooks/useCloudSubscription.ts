import { hasPaidSubscription } from "@/lib/api/domains/billing/types";
import { useBillingInformation } from "@/lib/api/domains/billing/hooks";
import { appSettings } from "@/lib/settings";

/**
 * Returns whether the current tenant has an active paid subscription on cloud.
 *
 * Self-hosted deployments always return true (no billing gate).
 * Cloud deployments check billing status via the billing API.
 * Returns true while loading to avoid flashing the upgrade prompt.
 */
export function useCloudSubscription(): boolean {
  const { data: billingData, isLoading } = useBillingInformation();

  if (!appSettings.NEXT_PUBLIC_CLOUD_ENABLED) {
    return true;
  }

  // Treat loading as subscribed to avoid UI flash
  if (isLoading || billingData == null) {
    return true;
  }

  return hasPaidSubscription(billingData);
}
