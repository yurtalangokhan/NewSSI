import { SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED } from "@/lib/constants";
import { fetchStandardSettingsSS } from "@/components/settings/lib";
import { tServer } from "@/i18n/server";
import { resolveLocaleSS } from "@/lib/localeSS";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // `lng` is passed per-call rather than via `i18n.changeLanguage()`: this
  // runs on the server, and mutating the shared instance's language here
  // would race with concurrent requests from users with other locales.
  const locale = await resolveLocaleSS();

  // First check build-time constant (fast path)
  if (!SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED) {
    return (
      <div className="flex h-screen">
        <div className="mx-auto my-auto text-lg font-bold text-red-500">
          {tServer("errors.enterpriseGate.eeOnly", { lng: locale })}
        </div>
      </div>
    );
  }

  // Then check runtime license status (for license enforcement mode)
  // This allows gating EE features when user doesn't have a valid license
  try {
    const settingsResponse = await fetchStandardSettingsSS();
    if (settingsResponse?.ok) {
      const settings = await settingsResponse.json();
      if (settings.ee_features_enabled === false) {
        // When the app is in GATED_ACCESS (expired or missing license), defer
        // to the root layout's GatedContentWrapper which handles path-based
        // exemptions (e.g. allowing /admin/billing for license management).
        if (settings.application_status === "gated_access") {
          return children;
        }

        return (
          <div className="flex h-screen">
            <div className="mx-auto my-auto text-lg font-bold text-red-500">
              {tServer("errors.enterpriseGate.licenseRequired", {
                lng: locale,
              })}
            </div>
          </div>
        );
      }
    }
  } catch (error) {
    // If settings fetch fails, allow access (fail open for better UX)
    console.error("Failed to fetch settings for EE check:", error);
  }

  return children;
}
