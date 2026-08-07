import React from "react";
import { useTranslation } from "react-i18next";
import { InfoItem } from "./InfoItem";
import { statusToDisplay, BillingInformation } from "@/lib/billing";
import { formatDateShort } from "@/lib/dateUtils";

interface SubscriptionSummaryProps {
  billingInformation: BillingInformation;
}

export function SubscriptionSummary({
  billingInformation,
}: SubscriptionSummaryProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.billing.summary",
  });
  return (
    <div className="grid grid-cols-2 gap-4">
      <InfoItem
        title={t("subscriptionStatus")}
        value={statusToDisplay(billingInformation.status)}
      />
      <InfoItem
        title={t("seats")}
        value={billingInformation.seats?.toString() ?? "—"}
      />
      <InfoItem
        title={t("billingStart")}
        value={formatDateShort(billingInformation.current_period_start)}
      />
      <InfoItem
        title={t("billingEnd")}
        value={formatDateShort(billingInformation.current_period_end)}
      />
    </div>
  );
}
