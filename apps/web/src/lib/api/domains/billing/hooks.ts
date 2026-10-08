"use client";
import { billingEndpoints } from "@/lib/api/domains/billing/endpoints";

import useSWR from "swr";
import { appSettings } from "@/lib/settings";
import { BillingInformation } from "./types";
import { SubscriptionStatus } from "./types";
import { fetchBillingInfo } from "./api";
import { fetchTenantsBillingInfo } from "./api";

import { LicenseStatus } from "./types";
import { fetchBillingLicense } from "./api";

/**
 * Hook to fetch billing information from Stripe.
 *
 * Works for both cloud and self-hosted deployments:
 * - Cloud: fetches from /api/tenants/billing-information (legacy endpoint)
 * - Self-hosted: fetches from /api/admin/billing/billing-information
 *
 * Returns subscription status, seats, billing period, etc.
 *
 * @example
 * ```tsx
 * const { data, isLoading, error, refresh } = useBillingInformation();
 *
 * if (isLoading) return <Loading />;
 * if (error) return <Error />;
 * if (!data || !hasActiveSubscription(data)) return <NoSubscription />;
 *
 * return <BillingDetails billing={data} />;
 * ```
 */
export function useBillingInformation() {
  const { data, error, mutate, isLoading } = useSWR<
    BillingInformation | SubscriptionStatus
  >(
    appSettings.NEXT_PUBLIC_CLOUD_ENABLED
      ? billingEndpoints.tenantsBillingInfo.browserPath
      : billingEndpoints.billingInfo.browserPath,
    () =>
      appSettings.NEXT_PUBLIC_CLOUD_ENABLED
        ? fetchTenantsBillingInfo<BillingInformation>()
        : fetchBillingInfo<BillingInformation>(),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 30000,
      // Don't auto-retry on errors (circuit breaker will block requests anyway)
      shouldRetryOnError: false,
      // Keep previous data while revalidating to prevent UI flashing
      keepPreviousData: true,
    }
  );

  return {
    data,
    isLoading,
    error,
    refresh: mutate,
  };
}

/**
 * Hook to fetch license status for self-hosted deployments.
 *
 * Returns license information including seats, expiry, and status.
 * Only fetches for self-hosted deployments (cloud uses tenant auth instead).
 *
 * @example
 * ```tsx
 * const { data, isLoading, error, refresh } = useLicense();
 *
 * if (isLoading) return <Loading />;
 * if (error) return <Error />;
 * if (!data?.has_license) return <NoLicense />;
 *
 * return <LicenseDetails license={data} />;
 * ```
 */
export function useLicense() {
  // Only fetch license for self-hosted deployments
  // Cloud deployments use tenant-based auth, not license files
  const url = appSettings.NEXT_PUBLIC_CLOUD_ENABLED
    ? null
    : billingEndpoints.billingLicense.browserPath;

  const { data, error, mutate, isLoading } = useSWR<LicenseStatus>(
    url,
    () => fetchBillingLicense<LicenseStatus>(),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 30000,
      shouldRetryOnError: false,
      keepPreviousData: true,
    }
  );

  // Return empty state for cloud deployments
  if (appSettings.NEXT_PUBLIC_CLOUD_ENABLED) {
    return {
      data: null,
      isLoading: false,
      error: undefined,
      refresh: () => Promise.resolve(undefined),
    };
  }

  return {
    data,
    isLoading,
    error,
    refresh: mutate,
  };
}
