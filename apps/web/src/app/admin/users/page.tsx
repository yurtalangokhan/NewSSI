"use client";

import { useState } from "react";
import SimpleTabs from "@/refresh-components/SimpleTabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import SignedUpUserTable from "@/components/admin/users/SignedUpUserTable";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { InvitedUserSnapshot } from "@/lib/types";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import PendingUsersTable from "@/components/admin/users/PendingUsersTable";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { Spinner } from "@/components/Spinner";
import { SvgDownloadCloud } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.USERS]!;

interface CountDisplayProps {
  label: string;
  value: number | null;
  isLoading: boolean;
}

function CountDisplay({ label, value, isLoading }: CountDisplayProps) {
  const displayValue = isLoading
    ? "..."
    : value === null
      ? "-"
      : value.toLocaleString();

  return (
    <div className="flex items-center gap-1 px-1 py-0.5 rounded-06">
      <Text as="p" mainUiMuted text03>
        {label}
      </Text>
      <Text as="p" headingH3 text05>
        {displayValue}
      </Text>
    </div>
  );
}

function UsersTables({
  q,
  isDownloadingUsers,
  setIsDownloadingUsers,
}: {
  q: string;
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
      //Clean up URL after download to avoid memory leaks
      window.URL.revokeObjectURL(url);
      document.body.removeChild(anchor_tag);
    } catch (error) {
      toast.error(
        t("admin.users.downloadFailedError", { error: String(error) })
      );
    } finally {
      //Ensure spinner is visible for at least 1 second
      //This is to avoid the spinner disappearing too quickly
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
  // Show loading animation only during the initial data fetch
  const tabs = SimpleTabs.generateTabs({
    current: {
      name: t("admin.users.currentUsersTab"),
      content: (
        <Card className="w-full">
          <CardHeader>
            <div className="flex justify-between items-center gap-1">
              <CardTitle>{t("admin.users.currentUsersTitle")}</CardTitle>
              <Button
                leftIcon={SvgDownloadCloud}
                disabled={isDownloadingUsers}
                onClick={() => downloadAllUsers()}
              >
                {isDownloadingUsers
                  ? t("admin.users.downloadingButton")
                  : t("admin.users.downloadCsvButton")}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <SignedUpUserTable
              q={q}
              countDisplay={
                <CountDisplay
                  label={t("admin.users.totalUsersLabel")}
                  value={currentUsersCount}
                  isLoading={currentUsersLoading}
                />
              }
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
      ),
    },
    ...(NEXT_PUBLIC_CLOUD_ENABLED && {
      pending: {
        name: t("admin.users.pendingUsersTab"),
        content: (
          <Card>
            <CardHeader>
              <div className="flex justify-between items-center gap-1">
                <CardTitle>{t("admin.users.pendingUsersTitle")}</CardTitle>
                <CountDisplay
                  label={t("admin.users.totalPendingLabel")}
                  value={pendingUsersCount}
                  isLoading={pendingUsersLoading}
                />
              </div>
            </CardHeader>
            <CardContent>
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

  return <SimpleTabs tabs={tabs} defaultValue="current" />;
}

function SearchableTables() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [isDownloadingUsers, setIsDownloadingUsers] = useState(false);

  return (
    <div>
      {isDownloadingUsers && <Spinner />}
      <div className="flex flex-col gap-y-4">
        <div className="flex flex-row items-center gap-2">
          <InputTypeIn
            placeholder={t("admin.users.searchPlaceholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <AddUserButton />
        </div>
        <UsersTables
          q={query}
          isDownloadingUsers={isDownloadingUsers}
          setIsDownloadingUsers={setIsDownloadingUsers}
        />
      </div>
    </div>
  );
}

function AddUserButton() {
  const { t } = useTranslation();

  return (
    <CreateButton primary href="/admin/users/add">
      {t("admin.users.addUserButton")}
    </CreateButton>
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
