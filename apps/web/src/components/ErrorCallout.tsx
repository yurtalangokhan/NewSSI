"use client";

import { Callout } from "@/components/ui/callout";
import { SvgAlertTriangle } from "@/icons";
import i18n from "@/i18n/config";

export function formatErrorMessage(rawError: unknown): string {
  if (!rawError) return "";
  let msg =
    typeof rawError === "string"
      ? rawError
      : (rawError as any)?.message || String(rawError);

  if (
    typeof msg === "string" &&
    msg.includes("An error occurred while fetching the data")
  ) {
    msg = msg.replace(
      "An error occurred while fetching the data",
      i18n.t("common.fetchError", {
        defaultValue: "Veriler alınırken bir hata oluştu.",
      })
    );
  }

  return msg;
}

export function ErrorCallout({
  errorTitle,
  errorMsg,
}: {
  errorTitle?: string;
  errorMsg?: string;
}) {
  const formatted = formatErrorMessage(errorMsg);
  return (
    <div>
      <Callout
        className="mt-4"
        title={
          errorTitle ||
          i18n.t("common.pageNotFound", {
            defaultValue: "Sayfa bulunamadı",
          })
        }
        icon={<SvgAlertTriangle className="h-5 w-5 stroke-status-error-05" />}
        type="danger"
      >
        {formatted}
      </Callout>
    </div>
  );
}
