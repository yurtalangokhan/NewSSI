"use client";

import { useEffect } from "react";
import { toast } from "@/hooks/useToast";
import {
  createCustomerPortalSession,
  useBillingInformation,
  hasActiveSubscription,
} from "@/lib/billing";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import Button from "@/refresh-components/buttons/Button";
import { SubscriptionSummary } from "./SubscriptionSummary";
import { BillingAlerts } from "./BillingAlerts";
import { SvgClipboard, SvgWallet } from "@opal/icons";
import { useTranslation } from "react-i18next";

export default function BillingInformationPage() {
  const { t } = useTranslation();
  const {
    data: billingInformation,
    error,
    isLoading,
  } = useBillingInformation();

  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("session_id")) {
      toast.success(t("ee.billing.updatedSuccess"));
      url.searchParams.delete("session_id");
      window.history.replaceState({}, "", url.toString());
    }
  }, [t]);

  if (isLoading) {
    return (
      <div className="text-center py-8">{t("ee.billing.loading")}</div>
    );
  }

  if (error) {
    console.error("Failed to fetch billing information:", error);
    return (
      <div className="text-center py-8 text-red-500">
        {t("ee.billing.errorLoading")}
      </div>
    );
  }

  if (!billingInformation || !hasActiveSubscription(billingInformation)) {
    return (
      <div className="text-center py-8">{t("ee.billing.noInformation")}</div>
    );
  }

  const handleManageSubscription = async () => {
    try {
      const response = await createCustomerPortalSession();
      console.log("response", response);
      if (!response.stripe_customer_portal_url) {
        throw new Error("No portal URL returned from the server");
      }
      window.location.href = response.stripe_customer_portal_url;
    } catch (error) {
      console.error("Error creating customer portal session:", error);
      toast.error(t("ee.billing.portalError"));
    }
  };

  return (
    <div className="space-y-8">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl font-bold flex items-center">
            <SvgWallet className="mr-4 text-muted-foreground h-6 w-6" />
            {t("ee.billing.subscriptionDetails")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <SubscriptionSummary billingInformation={billingInformation} />
          <BillingAlerts billingInformation={billingInformation} />
        </CardContent>
      </Card>

      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-xl font-semibold">
            {t("ee.billing.manageSubscription")}
          </CardTitle>
          <CardDescription>
            {t("ee.billing.manageDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={handleManageSubscription}
            className="w-full"
            leftIcon={SvgClipboard}
          >
            {t("ee.billing.manageSubscription")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
