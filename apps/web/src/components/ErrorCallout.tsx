"use client";

import { Callout } from "@/components/ui/callout";
import { FiAlertTriangle } from "react-icons/fi";
import i18n from "@/i18n/config";

export function formatErrorMessage(rawError: unknown): string {
  if (!rawError) return "";
  let msg =
    typeof rawError === "string"
      ? rawError
      : (rawError as any)?.message || String(rawError);

  if (
    typeof msg === "string" &&
    msg.trim().startsWith("{") &&
    msg.trim().endsWith("}")
  ) {
    try {
      const parsed = JSON.parse(msg);
      if (parsed.message) {
        let parsedMsg = parsed.message;
        if (
          parsedMsg === "An invalid response was received from the upstream server" ||
          parsedMsg.includes("upstream server")
        ) {
          parsedMsg = i18n.t("common.upstreamServerInvalidResponse", {
            defaultValue: "Üst sunucudan geçersiz bir yanıt alındı.",
          });
        }
        msg = parsed.request_id
          ? `${parsedMsg} (İstek Kimliği: ${parsed.request_id})`
          : parsedMsg;
      }
    } catch {
      // Keep original msg
    }
  }

  if (typeof msg === "string") {
    if (
      msg === "An invalid response was received from the upstream server" ||
      msg.includes("An invalid response was received from the upstream server")
    ) {
      msg = msg.replace(
        "An invalid response was received from the upstream server",
        i18n.t("common.upstreamServerInvalidResponse", {
          defaultValue: "Üst sunucudan geçersiz bir yanıt alındı.",
        })
      );
    }
    if (msg.includes("An error occurred while fetching the data")) {
      msg = msg.replace(
        "An error occurred while fetching the data",
        i18n.t("common.fetchError", {
          defaultValue: "Veriler alınırken bir hata oluştu.",
        })
      );
    }
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
          i18n.t("common.pageNotFound", { defaultValue: "Sayfa bulunamadı" })
        }
        icon={<FiAlertTriangle className="text-red-500 h-5 w-5" />}
        type="danger"
      >
        {formatted}
      </Callout>
    </div>
  );
}
