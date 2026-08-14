"use client";

import { useState, useMemo, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Section } from "@/layouts/general-layouts";
import * as InputLayouts from "@/layouts/input-layouts";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import Card from "@/refresh-components/cards/Card";
import Separator from "@/refresh-components/Separator";
import { SvgUsers, SvgCheck } from "@opal/icons";
import { createCheckoutSession } from "@/lib/billing/svc";
import { useUser } from "@/providers/UserProvider";
import { formatDateShort } from "@/lib/dateUtils";
import type { PlanType } from "@/lib/billing/interfaces";
import InputNumber from "@/refresh-components/inputs/InputNumber";
import useUsers from "@/hooks/useUsers";

// ----------------------------------------------------------------------------
// BillingOption
// ----------------------------------------------------------------------------

interface BillingOptionProps {
  selected: boolean;
  onClick: () => void;
  title: string;
  price: number;
  badge?: string;
}

function BillingOption({
  selected,
  onClick,
  title,
  price,
  badge,
}: BillingOptionProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.billing.checkout",
  });
  return (
    <Card
      onClick={onClick}
      className="billing-option"
      data-selected={selected}
      padding={0}
    >
      <Section
        flexDirection="row"
        gap={0.5}
        height="fit"
        justifyContent="between"
        alignItems="start"
      >
        <Section
          alignItems="start"
          justifyContent="center"
          gap={0}
          height="fit"
          width="fit"
        >
          <Text mainUiAction className="billing-option-title">
            {title}
          </Text>
          <div className="billing-option-price">
            <Text mainContentEmphasis text04>
              ${price}
            </Text>
            <Text secondaryBody text03 nowrap>
              {t("perSeatMonth")}
            </Text>
          </div>
        </Section>
        {badge && (
          <Section
            flexDirection="row"
            gap={0.25}
            alignItems="center"
            justifyContent="end"
            width="fit"
            height="fit"
          >
            <Text secondaryAction className="billing-option-badge">
              {badge}
            </Text>
            <SvgCheck className="billing-option-check" />
          </Section>
        )}
      </Section>
    </Card>
  );
}

// ----------------------------------------------------------------------------
// CheckoutView
// ----------------------------------------------------------------------------

interface CheckoutViewProps {
  onAdjustPlan: () => void;
}

export default function CheckoutView({ onAdjustPlan }: CheckoutViewProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.billing.checkout",
  });
  const { user } = useUser();
  const { data: usersData } = useUsers({ includeApiKeys: false });

  // Calculate minimum required seats based on current active users
  const acceptedUsers =
    usersData?.accepted?.filter((u) => u.is_active).length ?? 0;
  const slackUsers =
    usersData?.slack_users?.filter((u) => u.is_active).length ?? 0;
  const minRequiredSeats = Math.max(1, acceptedUsers + slackUsers);

  const [billingPeriod, setBillingPeriod] = useState<PlanType>("annual");
  const [seats, setSeats] = useState(minRequiredSeats);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Update seats if minRequiredSeats changes (e.g., after user data loads)
  useEffect(() => {
    if (seats < minRequiredSeats) {
      setSeats(minRequiredSeats);
    }
  }, [minRequiredSeats, seats]);

  const monthlyPrice = 25;
  const annualPrice = 20;
  const annualPriceSelected = billingPeriod === "annual";

  const trialEndDate = useMemo(() => {
    const date = new Date();
    date.setMonth(date.getMonth() + 1);
    return formatDateShort(date.toISOString());
  }, []);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      const response = await createCheckoutSession({
        billing_period: billingPeriod,
        seats,
        email: user?.email,
      });

      if (response.stripe_checkout_url) {
        window.location.href = response.stripe_checkout_url;
      } else {
        throw new Error(t("invalidCheckoutResponse"));
      }
    } catch (err) {
      console.error("Error creating checkout session:", err);
      setError(err instanceof Error ? err.message : t("checkoutSessionFailed"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card padding={0} gap={0} alignItems="stretch">
      {/* Header */}
      <Section
        flexDirection="row"
        justifyContent="between"
        alignItems="start"
        padding={1}
        height="auto"
      >
        <Section
          flexDirection="column"
          alignItems="start"
          gap={0.25}
          height="auto"
          width="fit"
        >
          <SvgUsers size={24} />
          <Text headingH2 text04>
            {t("planName")}
          </Text>
        </Section>
        <Button secondary onClick={onAdjustPlan}>
          {t("adjustPlanButton")}
        </Button>
      </Section>

      {/* Content */}
      <div className="billing-content-area">
        <Section
          flexDirection="column"
          alignItems="stretch"
          gap={1}
          padding={1}
          height="auto"
        >
          {/* Billing Cycle */}
          <InputLayouts.Horizontal
            title={t("billingCycleTitle")}
            description={t("billingCycleDescription")}
          >
            <Section
              flexDirection="row"
              gap={0.25}
              width="fit"
              height="auto"
              justifyContent="start"
            >
              <BillingOption
                selected={billingPeriod === "monthly"}
                onClick={() => setBillingPeriod("monthly")}
                title={t("monthlyLabel")}
                price={monthlyPrice}
              />
              <BillingOption
                selected={billingPeriod === "annual"}
                onClick={() => setBillingPeriod("annual")}
                title={t("annualLabel")}
                price={annualPrice}
                badge={t("annualBadge")}
              />
            </Section>
          </InputLayouts.Horizontal>

          <Separator noPadding />

          {/* Seats */}
          <InputLayouts.Horizontal
            title={t("seatsTitle")}
            description={t("seatsDescription", {
              count: minRequiredSeats,
            })}
          >
            <InputNumber
              value={seats}
              onChange={setSeats}
              min={minRequiredSeats}
              defaultValue={minRequiredSeats}
              showReset
            />
          </InputLayouts.Horizontal>
        </Section>
      </div>

      {/* Footer */}
      <Section
        flexDirection="row"
        alignItems="center"
        justifyContent="between"
        padding={1}
        height="auto"
      >
        {error ? (
          <Text secondaryBody className="billing-error-text">
            {error}
          </Text>
        ) : !annualPriceSelected ? (
          <Text secondaryBody text03>
            {t("billedOnPrefix")}{" "}
            <Text secondaryBody text04>
              {trialEndDate}
            </Text>{" "}
            {t("billedOnSuffix")}
          </Text>
        ) : (
          // Empty div to maintain space-between alignment
          <div></div>
        )}
        <Button main primary onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting ? t("loadingButton") : t("continueToPaymentButton")}
        </Button>
      </Section>
    </Card>
  );
}
