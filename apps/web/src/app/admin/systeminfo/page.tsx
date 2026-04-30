"use client";
import { NotebookIcon } from "@/components/icons/icons";
import { getWebVersion, getBackendVersion } from "@/lib/version";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SYSTEM_INFO]!;

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
    <div>
      <div className="border-solid border-background-600 border-b pb-2 mb-4 flex">
        <NotebookIcon size={32} />
        <h1 className="text-3xl font-bold pl-2">{t("admin.systemInfo.title")}</h1>
      </div>

      <div>
        <div className="flex mb-2">
          <p className="my-auto mr-1">{t("admin.systemInfo.backendVersion")}: </p>
          <p className="text-base my-auto text-slate-400 italic">
            {backend_version}
          </p>
        </div>
        <div className="flex mb-2">
          <p className="my-auto mr-1">{t("admin.systemInfo.webVersion")}: </p>
          <p className="text-base my-auto text-slate-400 italic">
            {web_version}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Page;
