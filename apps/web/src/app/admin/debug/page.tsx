"use client";

import { useState, useEffect } from "react";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ThreeDotsLoader } from "@/components/Loading";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import Button from "@/refresh-components/buttons/Button";
import { Card } from "@/components/ui/card";
import Text from "@/components/ui/text";
import { Spinner } from "@/components/Spinner";
import { SvgDownloadCloud } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DEBUG]!;

function Main() {
  const [categories, setCategories] = useState<string[]>([]);
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const response = await fetch("/api/admin/long-term-logs");
        if (!response.ok) throw new Error("Failed to fetch categories");
        const data = await response.json();
        setCategories(data);
      } catch (error) {
        console.error("Error fetching categories:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchCategories();
  }, []);

  const handleDownload = async (category: string) => {
    setIsDownloading(true);
    try {
      const response = await fetch(
        `/api/admin/long-term-logs/${category}/download`
      );
      if (!response.ok) throw new Error("Failed to download logs");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = `${category}-logs.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("Error downloading logs:", error);
    } finally {
      setIsDownloading(false);
    }
  };

  if (isLoading) {
    return <ThreeDotsLoader />;
  }

  return (
    <>
      {isDownloading && <Spinner />}
      <div className="mb-8">
        <Text className="mb-3">
          <b>{t("admin.debug.logsTitle")}</b> {t("admin.debug.description")}
        </Text>

        {categories.length > 0 && (
          <Card className="mt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("admin.debug.categoryHeader")}</TableHead>
                  <TableHead>{t("admin.debug.actionsHeader")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {categories.map((category) => (
                  <TableRow
                    key={category}
                    className="hover:bg-transparent dark:hover:bg-transparent"
                  >
                    <TableCell className="font-medium">{category}</TableCell>
                    <TableCell>
                      <Button
                        onClick={() => handleDownload(category)}
                        secondary
                        leftIcon={SvgDownloadCloud}
                      >
                        {t("admin.debug.downloadLogs")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </>
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
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.debug.workspaceTitle", {
            defaultValue: "Diagnostics workspace",
          })}
          description={t("admin.debug.workspaceDescription", {
            defaultValue:
              "Review log categories and download diagnostics when platform behavior needs investigation.",
          })}
          metrics={[
            {
              label: t("admin.debug.logCategoriesLabel", {
                defaultValue: "Log categories",
              }),
              value: t("admin.debug.availableBelow", {
                defaultValue: "Available below",
              }),
            },
            {
              label: t("admin.debug.exportLabel", {
                defaultValue: "Export",
              }),
              value: t("admin.debug.downloadLogs", {
                defaultValue: "Download logs",
              }),
            },
            {
              label: t("admin.debug.sensitiveLabel", {
                defaultValue: "Sensitive",
              }),
              value: t("admin.debug.adminOnly", {
                defaultValue: "Admin only",
              }),
              tone: "warning",
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.systemInfo.sidebar", {
                defaultValue: "System Information",
              }),
              href: ADMIN_PATHS.SYSTEM_INFO,
            },
            {
              label: t("admin.navigation.routes.systemSettings.sidebar", {
                defaultValue: "System Settings",
              }),
              href: ADMIN_PATHS.SYSTEM_SETTINGS,
              primary: true,
            },
          ]}
        />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
