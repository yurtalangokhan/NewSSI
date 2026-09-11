"use client";

import { UserGroupsTable } from "./UserGroupsTable";
import UserGroupCreationForm from "./UserGroupCreationForm";
import { useState } from "react";
import TableSkeleton from "@/refresh-components/skeletons/TableSkeleton";
import { useConnectorStatus, useUserGroups } from "@/lib/hooks";
import useUsers from "@/hooks/useUsers";
import { useUser } from "@/providers/UserProvider";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.GROUPS]!;

function Main() {
  const [showForm, setShowForm] = useState(false);
  const { t } = useTranslation();

  const { data, isLoading, error, refreshUserGroups } = useUserGroups();

  const {
    data: ccPairs,
    isLoading: isCCPairsLoading,
    error: ccPairsError,
  } = useConnectorStatus();

  const {
    data: users,
    isLoading: userIsLoading,
    error: usersError,
  } = useUsers({ includeApiKeys: true });

  const { isAdmin } = useUser();

  if (isLoading || isCCPairsLoading || userIsLoading) {
    return (
      <div className="p-6">
        <TableSkeleton
          rowCount={5}
          columns={[
            { type: "text", width: "w-44", headerWidth: "w-24" },
            { type: "badge", width: "w-20", headerWidth: "w-16" },
            { type: "badge", width: "w-20", headerWidth: "w-16" },
            { type: "actions", width: "w-20", headerWidth: "w-16" },
          ]}
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-red-600">{t("admin.groups.errorLoadingGroups")}</div>
    );
  }

  if (ccPairsError || !ccPairs) {
    return (
      <div className="text-red-600">
        {t("admin.groups.errorLoadingConnectors")}
      </div>
    );
  }

  if (usersError || !users) {
    return (
      <div className="text-red-600">{t("admin.groups.errorLoadingUsers")}</div>
    );
  }

  return (
    <>
      {isAdmin && (
        <CreateButton onClick={() => setShowForm(true)}>
          {t("admin.groups.createButton")}
        </CreateButton>
      )}
      {data.length > 0 && (
        <div className="mt-2">
          <UserGroupsTable userGroups={data} refresh={refreshUserGroups} />
        </div>
      )}
      {showForm && (
        <UserGroupCreationForm
          onClose={() => {
            refreshUserGroups();
            setShowForm(false);
          }}
          users={users.accepted}
          ccPairs={ccPairs}
        />
      )}
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
