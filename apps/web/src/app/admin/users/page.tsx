"use client";

import { useState } from "react";
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
import { Spinner } from "@/components/Spinner";
import { SvgDownloadCloud, SvgPlus } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import useDebouncedValue from "@/hooks/useDebouncedValue";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

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

  return (
    <>
      <AdminOverviewPanel
        icon={route.icon}
        title={t("admin.users.workspaceTitle")}
        description={t("admin.users.workspaceDescription")}
        metrics={[
          {
            label: t("admin.users.matchingUsersLabel"),
            value: currentUsersLoading
              ? "..."
              : (currentUsersCount ?? 0).toLocaleString(),
            tone:
              !currentUsersLoading && (currentUsersCount ?? 0) > 0
                ? "success"
                : "warning",
          },
          {
            label: t("admin.users.pendingRequestsLabel"),
            value: NEXT_PUBLIC_CLOUD_ENABLED
              ? pendingUsersLoading
                ? "..."
                : (pendingUsersCount ?? 0).toLocaleString()
              : t("admin.users.notAvailable"),
            tone:
              NEXT_PUBLIC_CLOUD_ENABLED && (pendingUsersCount ?? 0) > 0
                ? "warning"
                : "neutral",
          },
          {
            label: t("admin.users.rolesAvailableLabel"),
            value: rolesLoading ? "..." : String(rolesData?.roles?.length ?? 0),
          },
        ]}
        actions={[
          {
            label: t("admin.navigation.routes.roles.sidebar"),
            href: ADMIN_PATHS.ROLES,
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
      {isDownloadingUsers && <Spinner />}
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
        icon={route.icon}
        separator
      />
      <SettingsLayouts.Body>
        <SearchableTables />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
