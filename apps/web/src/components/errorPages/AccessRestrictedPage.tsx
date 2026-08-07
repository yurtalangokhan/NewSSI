"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n/config";
import Link from "next/link";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import Button from "@/refresh-components/buttons/Button";
import InlineExternalLink from "@/refresh-components/InlineExternalLink";
import { logout } from "@/lib/user";
import { loadStripe } from "@stripe/stripe-js";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import { useLicense } from "@/hooks/useLicense";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { ApplicationStatus } from "@/interfaces/settings";
import Text from "@/refresh-components/texts/Text";
import { SvgLock } from "@opal/icons";
import { APP_NAME, APP_SUPPORT_EMAIL } from "@/lib/appInfo";

const linkClassName = "text-action-link-05 hover:text-action-link-06 underline";

const fetchStripePublishableKey = async (): Promise<string> => {
  const response = await fetch("/api/tenants/stripe-publishable-key");
  if (!response.ok) {
    throw new Error(i18n.t("errors.accessRestricted.fetchStripeKeyFailed"));
  }
  const data = await response.json();
  return data.publishable_key;
};

const fetchResubscriptionSession = async () => {
  const response = await fetch("/api/tenants/create-subscription-session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(i18n.t("errors.accessRestricted.fetchResubFailed"));
  }
  return response.json();
};

export default function AccessRestricted() {
  const { t } = useTranslation("common", {
    keyPrefix: "errors.accessRestricted",
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: license } = useLicense();
  const settings = useSettingsContext();

  const isSeatLimitExceeded =
    settings.settings.application_status ===
    ApplicationStatus.SEAT_LIMIT_EXCEEDED;
  const hadPreviousLicense = license?.has_license === true;
  const showRenewalMessage = NEXT_PUBLIC_CLOUD_ENABLED || hadPreviousLicense;

  function getSeatLimitMessage() {
    const { used_seats, seat_count } = settings.settings;
    const counts =
      used_seats != null && seat_count != null
        ? t("seatCountsSuffix", { used: used_seats, total: seat_count })
        : "";
    return t("seatLimitMessage", { counts });
  }

  const initialModalMessage = isSeatLimitExceeded
    ? getSeatLimitMessage()
    : showRenewalMessage
      ? NEXT_PUBLIC_CLOUD_ENABLED
        ? t("suspendedCloud", { appName: APP_NAME })
        : t("suspendedLicense", { appName: APP_NAME })
      : t("licenseRequired", { appName: APP_NAME });

  const handleResubscribe = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const publishableKey = await fetchStripePublishableKey();
      const { sessionId } = await fetchResubscriptionSession();
      const stripe = await loadStripe(publishableKey);

      if (stripe) {
        await stripe.redirectToCheckout({ sessionId });
      } else {
        throw new Error(t("stripeLoadFailed"));
      }
    } catch (error) {
      console.error("Error creating resubscription session:", error);
      setError(t("resubscribeError"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ErrorPageLayout>
      <div className="flex items-center gap-2">
        <Text headingH2>{t("title")}</Text>
        <SvgLock className="stroke-status-error-05 w-[1.5rem] h-[1.5rem]" />
      </div>

      <Text text03>{initialModalMessage}</Text>

      {isSeatLimitExceeded ? (
        <>
          <Text text03>
            {t("seatLimitAdminPrefix")}{" "}
            <Link className={linkClassName} href="/admin/users">
              {t("userManagementLink")}
            </Link>{" "}
            {t("seatLimitAdminMiddle")}{" "}
            <Link className={linkClassName} href="/admin/billing">
              {t("adminBillingLink")}
            </Link>{" "}
            {t("seatLimitAdminSuffix")}
          </Text>

          <div className="flex flex-row gap-2">
            <Button
              onClick={async () => {
                await logout();
              }}
            >
              {t("logOutButton")}
            </Button>
          </div>
        </>
      ) : NEXT_PUBLIC_CLOUD_ENABLED ? (
        <>
          <Text text03>{t("reinstateCloudBody", { appName: APP_NAME })}</Text>

          <Text text03>{t("manageSubscriptionBody")}</Text>

          <div className="flex flex-row gap-2">
            <Button onClick={handleResubscribe} disabled={isLoading}>
              {isLoading ? t("loadingButton") : t("resubscribeButton")}
            </Button>
            <Button
              secondary
              onClick={async () => {
                await logout();
              }}
            >
              {t("logOutButton")}
            </Button>
          </div>

          {error && <Text className="text-status-error-05">{error}</Text>}
        </>
      ) : (
        <>
          <Text text03>
            {hadPreviousLicense
              ? t("reinstateLicenseBody", { appName: APP_NAME })
              : t("getStartedBody")}
          </Text>

          <Text text03>
            {t("billingVisitPrefix")}{" "}
            <Link className={linkClassName} href="/admin/billing">
              {t("adminBillingLink")}
            </Link>{" "}
            {hadPreviousLicense
              ? t("billingVisitMiddleRenew")
              : t("billingVisitMiddleActivate")}{" "}
            {t("billingVisitSuffixPrefix")}{" "}
            <a className={linkClassName} href={`mailto:${APP_SUPPORT_EMAIL}`}>
              {APP_SUPPORT_EMAIL}
            </a>{" "}
            {t("billingVisitSuffixSuffix")}
          </Text>

          <div className="flex flex-row gap-2">
            <Button
              onClick={async () => {
                await logout();
              }}
            >
              {t("logOutButton")}
            </Button>
          </div>
        </>
      )}

      <Text text03>
        {t("needHelpPrefix")}{" "}
        <InlineExternalLink
          className={linkClassName}
          href="https://discord.gg/4NA5SbzrWb"
        >
          {t("discordCommunityLink")}
        </InlineExternalLink>{" "}
        {t("needHelpSuffix")}
      </Text>
    </ErrorPageLayout>
  );
}
