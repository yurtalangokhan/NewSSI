export const billingEndpoints = {
  billingInfo: { browserPath: "/api/admin/billing/billing-information" },
  billingLicense: { browserPath: "/api/license" },
  tenantsBillingInfo: { browserPath: "/api/tenants/billing-information" },
  billingAction: (
    cloudEnabled: boolean,
    action: string
  ): { browserPath: string } => {
    const base = cloudEnabled ? "/api/tenants" : "/api/admin/billing";
    return { browserPath: `${base}/${action}` };
  },
  licenseAction: (action: string): { browserPath: string } => {
    return { browserPath: `/api/license/${action}` };
  },
  licenseClaim: (sessionId?: string): { browserPath: string } => {
    const path = billingEndpoints.licenseAction("claim").browserPath;
    return {
      browserPath: sessionId
        ? `${path}?session_id=${encodeURIComponent(sessionId)}`
        : path,
    };
  },
  fetchSubscriptionStripeKey: {
    browserPath: "/api/tenants/stripe-publishable-key",
  },
  createResubscriptionSession: {
    browserPath: "/api/tenants/create-subscription-session",
  },
} as const;
