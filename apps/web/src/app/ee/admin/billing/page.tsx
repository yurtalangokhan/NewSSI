"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import BillingInformationPage from "./BillingInformationPage";
import { SvgCreditCard } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface BillingInformation {
  stripe_subscription_id: string;
  status: string;
  current_period_start: Date;
  current_period_end: Date;
  number_of_seats: number;
  cancel_at_period_end: boolean;
  canceled_at: Date | null;
  trial_start: Date | null;
  trial_end: Date | null;
  seats: number;
  payment_method_enabled: boolean;
}

export default function page() {
  const { t } = useTranslation("common", { keyPrefix: "admin" });

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgCreditCard}
        title={t("billing.pageTitle")}
        description={t("billing.description", {
          defaultValue:
            "Manage your subscription plan, seat licenses, and billing details.",
        })}
        separator
      />
      <SettingsLayouts.Body>
        <BillingInformationPage />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
