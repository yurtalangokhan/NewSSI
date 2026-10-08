import { billingEndpoints } from "@/lib/api/domains/billing/endpoints";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";

import { appSettings } from "@/lib/settings";
import type {
  CreateCheckoutSessionRequest,
  CreateCheckoutSessionResponse,
  CreateCustomerPortalSessionRequest,
  CreateCustomerPortalSessionResponse,
  SeatUpdateRequest,
  SeatUpdateResponse,
} from "@/lib/api/domains/billing/types";

async function requestBillingJson<T>(path: string): Promise<T> {
  const res = await apiRequest(path);
  if (!res.ok)
    throw new Error(`Billing request failed (Status: ${res.status})`);
  const result = await parseJsonResponse<T>(res);
  if (result === undefined) {
    throw new Error("Billing request returned empty response");
  }
  return result;
}

export function fetchBillingInfo<T = unknown>(): Promise<T> {
  return requestBillingJson<T>(billingEndpoints.billingInfo.browserPath);
}

export function fetchBillingLicense<T = unknown>(): Promise<T> {
  return requestBillingJson<T>(billingEndpoints.billingLicense.browserPath);
}

export function fetchTenantsBillingInfo<T = unknown>(): Promise<T> {
  return requestBillingJson<T>(billingEndpoints.tenantsBillingInfo.browserPath);
}

async function postBillingAction<T>(
  action: string,
  body?: unknown
): Promise<T> {
  const response = await apiRequest(
    billingEndpoints.billingAction(
      appSettings.NEXT_PUBLIC_CLOUD_ENABLED,
      action
    )
      .browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }
  );
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(error.detail || "Billing request failed");
  }
  return response.json() as Promise<T>;
}

export function createCheckoutSession(request?: CreateCheckoutSessionRequest) {
  return postBillingAction<CreateCheckoutSessionResponse>(
    "create-checkout-session",
    request
  );
}

export function createCustomerPortalSession(
  request?: CreateCustomerPortalSessionRequest
) {
  return postBillingAction<CreateCustomerPortalSessionResponse>(
    "create-customer-portal-session",
    request
  );
}

export function updateSeatCount(request: SeatUpdateRequest) {
  return postBillingAction<SeatUpdateResponse>("seats/update", request);
}

export function resetStripeConnection() {
  return postBillingAction<{ success: boolean; message: string }>(
    "reset-connection"
  );
}

async function postSelfHostedLicense<T>(
  path: string,
  availabilityLabel: string,
  fallback: string,
  body?: BodyInit
): Promise<T> {
  if (appSettings.NEXT_PUBLIC_CLOUD_ENABLED) {
    throw new Error(`${availabilityLabel} is only available for self-hosted`);
  }
  const response = await apiRequest(path, { method: "POST", body });
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(error.detail || fallback);
  }
  return response.json() as Promise<T>;
}

export function claimLicense(sessionId?: string) {
  return postSelfHostedLicense<{ success: boolean; license?: unknown }>(
    billingEndpoints.licenseClaim(sessionId).browserPath,
    sessionId ? `/claim?session_id=${encodeURIComponent(sessionId)}` : "/claim",
    "License request failed"
  );
}

export function refreshLicenseCache() {
  return postSelfHostedLicense<{ success: boolean; message?: string }>(
    billingEndpoints.licenseAction("refresh").browserPath,
    "/refresh",
    "License request failed"
  );
}

export function uploadLicense(licenseKey: string) {
  const formData = new FormData();
  formData.append(
    "license_file",
    new Blob([licenseKey], { type: "text/plain" }),
    "license.txt"
  );
  return postSelfHostedLicense<{ success: boolean; message?: string }>(
    billingEndpoints.licenseAction("upload").browserPath,
    "/upload",
    "License upload failed",
    formData
  );
}

export function fetchSubscriptionStripeKey(): Promise<Response> {
  return apiRequest(billingEndpoints.fetchSubscriptionStripeKey.browserPath);
}

export function createResubscriptionSession(): Promise<Response> {
  return apiRequest(billingEndpoints.createResubscriptionSession.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
}
