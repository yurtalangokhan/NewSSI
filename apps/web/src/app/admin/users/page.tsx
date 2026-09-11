"use client";

import { useMemo, useState } from "react";
import SimpleTabs from "@/refresh-components/SimpleTabs";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import SignedUpUserTable from "@/components/admin/users/SignedUpUserTable";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { InvitedUserSnapshot } from "@/lib/types";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import PendingUsersTable from "@/components/admin/users/PendingUsersTable";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { SvgDownloadCloud, SvgPlus } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import useDebouncedValue from "@/hooks/useDebouncedValue";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { formatRoleName } from "@/lib/auth/roles";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.USERS]!;

function UsersTables({
  q,
  query,
  setQuery,
  isDownloadingUsers,
  setIsDownloadingUsers,
}: {
  q: string;
  query: string;
  setQuery: (val: string) => void;
  isDownloadingUsers: boolean;
  setIsDownloadingUsers: (loading: boolean) => void;
}) {
  const { t } = useTranslation();
  const [currentUsersCount, setCurrentUsersCount] = useState<number | null>(
    null
  );
  const [currentUsersLoading, setCurrentUsersLoading] = useState<boolean>(true);

  const downloadAllUsers = async () => {
    setIsDownloadingUsers(true);
    const startTime = Date.now();
    const minDurationMsForSpinner = 1000;
    try {
      const response = await fetch("/api/user-service/users/download/csv");
      if (!response.ok) {
        throw new Error(t("admin.users.downloadFailedError", { error: "" }));
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor_tag = document.createElement("a");
      anchor_tag.href = url;
      anchor_tag.download = "users.csv";
      document.body.appendChild(anchor_tag);
      anchor_tag.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(anchor_tag);
    } catch (error) {
      toast.error(
        t("admin.users.downloadFailedError", { error: String(error) })
      );
    } finally {
      const endTime = Date.now();
      const duration = endTime - startTime;
      await new Promise((resolve) =>
        setTimeout(resolve, minDurationMsForSpinner - duration)
      );
      setIsDownloadingUsers(false);
    }
  };

  const {
    data: pendingUsers,
    error: pendingUsersError,
    isLoading: pendingUsersLoading,
    mutate: pendingUsersMutate,
  } = useSWR<InvitedUserSnapshot[]>(
    NEXT_PUBLIC_CLOUD_ENABLED ? "/api/tenants/users/pending" : null,
    errorHandlingFetcher
  );
  const pendingUsersCount =
    pendingUsers === undefined ? null : pendingUsers.length;
  const { data: rolesData, isLoading: rolesLoading } = useSWR<{
    roles: { name: string }[];
  }>("/api/user-service/roles", errorHandlingFetcher);
  const { data: roleDistributionData, isLoading: roleDistributionLoading } =
    useSWR<{ distribution: { role: string; count: number }[] }>(
      "/api/user-service/users/role-distribution",
      errorHandlingFetcher
    );
  const distribution = roleDistributionData?.distribution ?? [];
  const roleCarouselValues = useMemo(
    () =>
      distribution
        .slice(0, 8)
        .map((r) => ({ value: `${formatRoleName(r.role)} · ${r.count}` })),
    [distribution]
  );

  const { data: activeUsersData, isLoading: activeUsersLoading } = useSWR<{
    total_items: number;
  }>("/api/user-service/users?is_active=true&limit=1", errorHandlingFetcher);
  const { data: inactiveUsersData, isLoading: inactiveUsersLoading } = useSWR<{
    total_items: number;
  }>("/api/user-service/users?is_active=false&limit=1", errorHandlingFetcher);
  const userStatusLoading = activeUsersLoading || inactiveUsersLoading;

  const currentUsersContent = (
    <Card className="w-full rounded-12 border-border-01 bg-background-neutral-00 shadow-none">
      <CardHeader className="border-b border-border-01 bg-background-neutral-01 p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Text as="p" headingH3 text05>
              {t("admin.users.currentUsersTitle")}
            </Text>
            {currentUsersCount !== null && (
              <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03 font-medium">
                {currentUsersCount.toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              secondary
              leftIcon={SvgDownloadCloud}
              disabled={isDownloadingUsers}
              onClick={() => downloadAllUsers()}
            >
              {isDownloadingUsers
                ? t("admin.users.downloadingButton")
                : t("admin.users.downloadCsvButton")}
            </Button>
            <Button primary href="/admin/users/add" leftIcon={SvgPlus}>
              {t("admin.users.addUserButton")}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <SignedUpUserTable
          q={q}
          query={query}
          onQueryChange={setQuery}
          onTotalItemsChange={(count) => setCurrentUsersCount(count)}
          onLoadingChange={(loading) => {
            setCurrentUsersLoading(loading);
            if (loading) {
              setCurrentUsersCount(null);
            }
          }}
        />
      </CardContent>
    </Card>
  );

  const tabs = SimpleTabs.generateTabs({
    current: {
      name: t("admin.users.currentUsersTab"),
      content: currentUsersContent,
    },
    ...(NEXT_PUBLIC_CLOUD_ENABLED && {
      pending: {
        name: t("admin.users.pendingUsersTab"),
        content: (
          <Card className="rounded-12 border-border-01 bg-background-neutral-00 shadow-none">
            <CardHeader className="border-b border-border-01 bg-background-neutral-01 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Text as="p" headingH3 text05>
                    {t("admin.users.pendingUsersTitle")}
                  </Text>
                  {pendingUsersCount !== null && (
                    <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03 font-medium">
                      {pendingUsersCount.toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button primary href="/admin/users/add" leftIcon={SvgPlus}>
                    {t("admin.users.addUserButton")}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="p-3 border-b border-border-01 bg-background-neutral-00">
                <InputTypeIn
                  leftSearchIcon
                  placeholder={t("admin.users.searchPlaceholder")}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onClear={() => setQuery("")}
                />
              </div>
              <PendingUsersTable
                users={pendingUsers || []}
                mutate={pendingUsersMutate}
                error={pendingUsersError}
                isLoading={pendingUsersLoading}
                q={q}
              />
            </CardContent>
          </Card>
        ),
      },
    }),
  });

  const isOverviewLoading =
    rolesLoading || roleDistributionLoading || userStatusLoading;

  return (
    <>
      <AdminOverviewPanel
        icon={route.icon}
        isLoading={isOverviewLoading}
        title={t("admin.users.workspaceTitle")}
        description={t("admin.users.workspaceDescription")}
        metrics={[
          {
            label: t("admin.users.userStatusLabel", {
              defaultValue: "User status",
            }),
            value: userStatusLoading
              ? "..."
              : `${(activeUsersData?.total_items ?? 0).toLocaleString()} ${t(
                  "admin.users.activeStatus"
                )} · ${(
                  inactiveUsersData?.total_items ?? 0
                ).toLocaleString()} ${t("admin.users.inactiveStatus")}`,
          },
          {
            label: t("admin.users.rolesAvailableLabel"),
            value: rolesLoading ? "..." : String(rolesData?.roles?.length ?? 0),
          },
          {
            label: t("admin.users.roleDistributionLabel", {
              defaultValue: "Role distribution",
            }),
            isLoading: roleDistributionLoading,
            value: roleDistributionLoading
              ? "..."
              : roleCarouselValues[0]?.value ??
                t("admin.users.noRoleData", { defaultValue: "No data" }),
            values:
              roleCarouselValues.length > 0
                ? roleCarouselValues
                : [
                    {
                      value: t("admin.users.noRoleData", {
                        defaultValue: "No data",
                      }),
                    },
                  ],
          },
        ]}
      />
      {NEXT_PUBLIC_CLOUD_ENABLED ? (
        <SimpleTabs tabs={tabs} defaultValue="current" />
      ) : (
        currentUsersContent
      )}
    </>
  );
}

function SearchableTables() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query.trim(), 250);
  const [isDownloadingUsers, setIsDownloadingUsers] = useState(false);

  return (
    <div>
      <div className="flex flex-col gap-y-3">
        <UsersTables
          q={debouncedQuery}
          query={query}
          setQuery={setQuery}
          isDownloadingUsers={isDownloadingUsers}
          setIsDownloadingUsers={setIsDownloadingUsers}
        />
      </div>
    </div>
  );
}

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        icon={route.icon}
        separator
      />
      <SettingsLayouts.Body>
        <SearchableTables />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
