"use client";

import { authenticatedFetch } from "@/lib/fetcher";

import { Label, SubLabel } from "@/components/Field";
import { toast } from "@/hooks/useToast";
import { getErrorMsg } from "@/lib/fetchUtils";
import { SettingsContext } from "@/providers/SettingsProvider";
import Button from "@/refresh-components/buttons/Button";
import { Callout } from "@/components/ui/callout";
import Text from "@/components/ui/text";
import { useContext, useState } from "react";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import { useTranslation } from "react-i18next";

export function CustomAnalyticsUpdateForm() {
  const { t } = useTranslation();
  const settings = useContext(SettingsContext);
  const customAnalyticsScript = settings?.customAnalyticsScript;

  const [newCustomAnalyticsScript, setNewCustomAnalyticsScript] =
    useState<string>(customAnalyticsScript || "");
  const [secretKey, setSecretKey] = useState<string>("");

  if (!settings) {
    return (
      <Callout
        type="danger"
        title={t("admin.performance.customAnalytics.fetchFailed")}
      ></Callout>
    );
  }

  return (
    <div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();

          const response = await authenticatedFetch(
            "/api/admin/enterprise-settings/custom-analytics-script",
            {
              method: "PUT",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                script: newCustomAnalyticsScript.trim(),
                secret_key: secretKey,
              }),
            }
          );
          if (response.ok) {
            toast.success("Custom analytics script updated successfully!");
          } else {
            const errorMsg = (await getErrorMsg(response)) ?? "Unknown error";
            toast.error(t("admin.performance.customAnalytics.updatedSuccess"));
          }
          setSecretKey("");
        }}
      >
        <div className="mb-4">
          <Label>{t("admin.performance.customAnalytics.scriptLabel")}</Label>
          <Text className="mb-3">
            {t("admin.performance.customAnalytics.scriptDescription")}
          </Text>
          <Text className="mb-2">
            {t("admin.performance.customAnalytics.scriptNotePrefix")}{" "}
            <span className="font-mono">&lt;script&gt;&lt;/script&gt;</span>{" "}
            {t("admin.performance.customAnalytics.scriptNoteSuffix")}
          </Text>
          <InputTextArea
            value={newCustomAnalyticsScript}
            onChange={(event) =>
              setNewCustomAnalyticsScript(event.target.value)
            }
          />
        </div>

        <Label>{t("admin.performance.customAnalytics.secretKeyLabel")}</Label>
        <SubLabel>
          <>
            {t("admin.performance.customAnalytics.secretKeyDescription")}{" "}
            {t("admin.performance.customAnalytics.secretKeyDescriptionSuffix")}
            <i>CUSTOM_ANALYTICS_SECRET_KEY</i> environment variable set when
            initially setting up Onyx.
          </>
        </SubLabel>
        <input
          className={`
            border
            border-border
            rounded
            w-full
            py-2
            px-3
            mt-1`}
          type="password"
          value={secretKey}
          onChange={(e) => setSecretKey(e.target.value)}
        />

        <Button className="mt-4" type="submit">
          {t("admin.performance.customAnalytics.updateButton")}
        </Button>
      </form>
    </div>
  );
}
