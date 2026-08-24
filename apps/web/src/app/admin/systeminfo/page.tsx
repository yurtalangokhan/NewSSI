"use client";

import { getWebVersion, getBackendVersion } from "@/lib/version";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SYSTEM_INFO]!;

function VersionRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-border-01 py-4 last:border-b-0 md:grid-cols-[180px_1fr]">
      <Text as="span" secondaryBody text04>
        {label}
      </Text>
      <Text as="span" mainUiBody text05 className="break-all">
        {value || "-"}
      </Text>
    </div>
  );
}

const Page = () => {
  const { t } = useTranslation();
  const [web_version, setWebVersion] = useState<string | null>(null);
  const [backend_version, setBackendVersion] = useState<string | null>(null);

  useEffect(() => {
    const fetchVersions = async () => {
      try {
        const [web, backend] = await Promise.all([
          getWebVersion(),
          getBackendVersion(),
        ]);
        setWebVersion(web);
        setBackendVersion(backend);
      } catch (e) {
        console.log(`Version info fetch failed for system info page - ${e}`);
      }
    };
    fetchVersions();
  }, []);

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        separator
      />

      <SettingsLayouts.Body>
        <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-4">
          <VersionRow
            label={t("admin.systemInfo.backendVersion")}
            value={backend_version}
          />
          <VersionRow
            label={t("admin.systemInfo.webVersion")}
            value={web_version}
          />
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
};

export default Page;
