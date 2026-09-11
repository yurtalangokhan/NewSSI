"use client";

import * as SettingsLayouts from "@/layouts/settings-layouts";
import { CUSTOM_ANALYTICS_ENABLED } from "@/lib/constants";
import { Callout } from "@/components/ui/callout";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import Text from "@/components/ui/text";
import { CustomAnalyticsUpdateForm } from "./CustomAnalyticsUpdateForm";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.CUSTOM_ANALYTICS]!;

function Main() {
  const { t } = useTranslation();

  if (!CUSTOM_ANALYTICS_ENABLED) {
    return (
      <div>
        <div className="mt-4">
          <Callout
            type="danger"
            title={t("admin.performance.customAnalytics.disabledTitle")}
          >
            {t("admin.performance.customAnalytics.disabledDescription")}{" "}
            <i>CUSTOM_ANALYTICS_SECRET_KEY</i> environment variable.
          </Callout>
        </div>
      </div>
    );
  }

  return (
    <div>
      <CustomAnalyticsUpdateForm />
    </div>
  );
}

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        separator
      />
      <SettingsLayouts.Body>
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
