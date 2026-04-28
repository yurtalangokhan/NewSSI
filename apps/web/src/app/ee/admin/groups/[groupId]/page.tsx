"use client";

import { use } from "react";
import { GroupDisplay } from "./GroupDisplay";
import { useSpecificUserGroup } from "./hook";
import { ThreeDotsLoader } from "@/components/Loading";
import { useConnectorStatus } from "@/lib/hooks";
import useUsers from "@/hooks/useUsers";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.GROUPS]!;

function Main({ groupId }: { groupId: string }) {
  const { t } = useTranslation();
  const {
    userGroup,
    isLoading: userGroupIsLoading,
    error: userGroupError,
    refreshUserGroup,
  } = useSpecificUserGroup(groupId);
  const {
    data: users,
    isLoading: userIsLoading,
    error: usersError,
  } = useUsers({ includeApiKeys: true });
  const {
    data: ccPairs,
    isLoading: isCCPairsLoading,
    error: ccPairsError,
  } = useConnectorStatus();

  if (userGroupIsLoading || userIsLoading || isCCPairsLoading) {
    return (
      <div className="h-full">
        <div className="my-auto">
          <ThreeDotsLoader />
        </div>
      </div>
    );
  }

  if (!userGroup || userGroupError) {
    return <div>{t("admin.groups.errorLoadingGroup")}</div>;
  }
  if (!users || usersError) {
    return <div>{t("admin.groups.errorLoadingUsers")}</div>;
  }
  if (!ccPairs || ccPairsError) {
    return <div>{t("admin.groups.errorLoadingConnectors")}</div>;
  }

  return (
    <>
      <SettingsLayouts.Header
        icon={route.icon}
        title={userGroup.name || t("admin.groups.unknownGroup")}
        separator
        backButton
      />

      <SettingsLayouts.Body>
        <GroupDisplay
          users={users.accepted}
          ccPairs={ccPairs}
          userGroup={userGroup}
          refreshUserGroup={refreshUserGroup}
        />
      </SettingsLayouts.Body>
    </>
  );
}

export default function Page(props: { params: Promise<{ groupId: string }> }) {
  const params = use(props.params);

  return (
    <SettingsLayouts.Root>
      <Main groupId={params.groupId} />
    </SettingsLayouts.Root>
  );
}
