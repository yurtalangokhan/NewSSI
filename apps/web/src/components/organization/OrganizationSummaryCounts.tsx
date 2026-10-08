"use client";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import useSWR from "swr";

import { fetchOrganizationPermissionCounts } from "@/lib/api/domains/access/api";
import { useTranslation } from "react-i18next";
import { SvgUsers, SvgCpu, SvgFolder } from "@/icons";
import Text from "@/refresh-components/texts/Text";
import Skeleton from "@/refresh-components/skeletons/Skeleton";
import { cn } from "@/lib/utils";

interface PermissionsResponse {
  permissions: Array<{ resource_id: string }>;
}
interface Props {
  organizationId: string;
  activeMembers: number;
  membersLoading: boolean;
}
export function OrganizationSummaryCounts({
  organizationId,
  activeMembers,
  membersLoading,
}: Props) {
  const { t, i18n } = useTranslation();
  // Share keys with the access editor so a successful save updates these counts.
  const agents = useSWR<PermissionsResponse>(
    accessEndpoints.scopedPermissions(
      organizationId,
      "organization",
      organizationId,
      "agent"
    ).browserPath,
    () => fetchOrganizationPermissionCounts(organizationId, "agent")
  );
  const collections = useSWR<PermissionsResponse>(
    accessEndpoints.scopedPermissions(
      organizationId,
      "organization",
      organizationId,
      "rag_collection"
    ).browserPath,
    () => fetchOrganizationPermissionCounts(organizationId, "rag_collection")
  );
  const distinctCount = (data?: PermissionsResponse) =>
    data
      ? new Set(data.permissions.map((permission) => permission.resource_id))
          .size
      : undefined;
  const items = [
    {
      label: t("admin.organizations.page.activeMembers"),
      icon: SvgUsers,
      count: activeMembers,
      loading: membersLoading,
      error: false,
    },
    {
      label: t("admin.organizations.access.agents"),
      icon: SvgCpu,
      count: distinctCount(agents.data),
      loading: agents.isLoading,
      error: agents.error,
    },
    {
      label: t("admin.organizations.access.collections"),
      icon: SvgFolder,
      count: distinctCount(collections.data),
      loading: collections.isLoading,
      error: collections.error,
    },
  ];
  return (
    <div className={cn("grid w-full max-w-sm grid-cols-3 gap-2 shrink-0")}>
      {items.map(({ label, icon: Icon, count, loading, error }) => {
        const state = loading
          ? t("admin.organizations.page.countsLoading")
          : error || count === undefined
            ? t("admin.organizations.page.countsUnavailable")
            : count.toLocaleString(i18n.language);
        return (
          <div
            key={label}
            aria-label={`${label}: ${state}`}
            aria-busy={Boolean(loading)}
            className={cn(
              "flex min-w-0 flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 px-3 py-2.5"
            )}
          >
            <div className={cn("flex items-center justify-between gap-2")}>
              <Icon
                aria-hidden="true"
                className={cn("h-4 w-4 shrink-0 stroke-text-03")}
              />
              {loading ? (
                <Skeleton className={cn("h-6 w-9")} aria-label={state} />
              ) : (
                <Text
                  headingH3
                  text04
                  as="p"
                  className={cn("tabular-nums leading-none")}
                  title={error ? state : undefined}
                >
                  {error || count === undefined ? "—" : state}
                </Text>
              )}
            </div>
            <Text
              secondaryBody
              text03
              as="p"
              className={cn("truncate")}
              title={label}
            >
              {label}
            </Text>
          </div>
        );
      })}
    </div>
  );
}
