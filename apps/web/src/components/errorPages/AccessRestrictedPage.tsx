"use client";
import { fetchSubscriptionStripeKey } from "@/lib/api/domains/billing/api";
import { createResubscriptionSession } from "@/lib/api/domains/billing/api";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Link from "next/link";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import Button from "@/refresh-components/buttons/Button";
import InlineExternalLink from "@/refresh-components/InlineExternalLink";
import { logout } from "@/lib/api/domains/session/api";
import { loadStripe } from "@stripe/stripe-js";
import { useLicense } from "@/lib/api/domains/billing/hooks";
import { appSettings } from "@/lib/settings";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { ApplicationStatus } from "@/interfaces/settings";
import Text from "@/refresh-components/texts/Text";
import { SvgLock } from "@opal/icons";
import i18n from "@/i18n/config";

const linkClassName = "text-action-link-05 hover:text-action-link-06 underline";

const fetchStripePublishableKey = async (): Promise<string> => {
  const response = await fetchSubscriptionStripeKey();
  if (!response.ok) {
    throw new Error(i18n.t("errors.accessRestricted.fetchStripeKeyFailed"));
  }
  const data = await response.json();
  return data.publishable_key;
};

const fetchResubscriptionSession = async () => {
  const response = await createResubscriptionSession();
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
  const showRenewalMessage =
    appSettings.NEXT_PUBLIC_CLOUD_ENABLED || hadPreviousLicense;

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
      ? appSettings.NEXT_PUBLIC_CLOUD_ENABLED
        ? t("suspendedCloud", { appName: appSettings.APP_NAME })
        : t("suspendedLicense", { appName: appSettings.APP_NAME })
      : t("licenseRequired", { appName: appSettings.APP_NAME });

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
      ) : appSettings.NEXT_PUBLIC_CLOUD_ENABLED ? (
        <>
          <Text text03>
            {t("reinstateCloudBody", { appName: appSettings.APP_NAME })}
          </Text>

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
              ? t("reinstateLicenseBody", { appName: appSettings.APP_NAME })
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
            <a
              className={linkClassName}
              href={`mailto:${appSettings.APP_SUPPORT_EMAIL}`}
            >
              {appSettings.APP_SUPPORT_EMAIL}
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
