"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";

import { usePersonaOptions } from "@/hooks/usePersonaOptions";
import { useCollections } from "@/lib/langconnect";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import {
  ResourceAssignmentPanel,
  type AssignableResource,
  type DirectResourcePermission,
} from "@/components/organization/ResourceAssignmentPanel";

export interface OrganizationAccessMember {
  id: string;
  user_id: string;
  role_in_org: string;
  is_active?: boolean;
  user?: {
    id: string;
    email?: string;
    first_name?: string;
    last_name?: string;
    username?: string;
  } | null;
}

interface OrganizationAccessPanelProps {
  organization: { id: string; name: string };
  members: OrganizationAccessMember[];
  editable: boolean;
  resourceType?: ResourceType;
  onSaveComplete?: () => void | Promise<void>;
}

interface ScopedPermissionsResponse {
  permissions: DirectResourcePermission[];
  count: number;
}

type TargetType = "organization" | "user";
export type ResourceType = "agent" | "rag_collection";

async function readErrorDetail(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as {
    detail?: string;
    message?: string;
  } | null;
  return data?.detail || data?.message || fallback;
}

async function permissionFetcher(
  url: string,
  fallback: string
): Promise<ScopedPermissionsResponse> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, fallback));
  }
  return response.json();
}

function memberLabel(member: OrganizationAccessMember) {
  const fullName = [member.user?.first_name, member.user?.last_name]
    .filter(Boolean)
    .join(" ");
  return (
    fullName || member.user?.email || member.user?.username || member.user_id
  );
}

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null) {
    const candidate = error as { info?: { detail?: string; message?: string } };
    return candidate.info?.detail || candidate.info?.message || fallback;
  }
  return fallback;
}

function ScopedResourcePanel({
  organizationId,
  targetType,
  targetId,
  resourceType,
  title,
  resources,
  editable,
  resourcesLoading,
  resourcesError,
  onRetryResources,
  onSaveComplete,
}: {
  organizationId: string;
  targetType: TargetType;
  targetId: string;
  resourceType: ResourceType;
  title: string;
  resources: AssignableResource[];
  editable: boolean;
  resourcesLoading: boolean;
  resourcesError?: string;
  onRetryResources?: () => void;
  onSaveComplete?: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const endpoint = `/api/user-service/permissions/organizations/${organizationId}/targets/${targetType}/${targetId}/resources/${resourceType}`;
  const { data, error, isLoading, mutate } = useSWR<ScopedPermissionsResponse>(
    endpoint,
    (url: string) =>
      permissionFetcher(
        url,
        t("admin.organizations.access.directPermissionsLoadFailed")
      )
  );

  async function save(permissions: DirectResourcePermission[]) {
    const response = await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permissions }),
    });
    if (!response.ok) {
      throw new Error(
        await readErrorDetail(
          response,
          t("admin.organizations.access.accessSaveFailed", { resource: title })
        )
      );
    }
    const saved = (await response.json()) as ScopedPermissionsResponse;
    await mutate(saved, { revalidate: false });
    try {
      await onSaveComplete?.();
    } catch {
      // Count refresh is ancillary; the permission PUT has already succeeded.
    }
    return saved.permissions;
  }

  const loadError = error
    ? errorMessage(
        error,
        t("admin.organizations.access.accessLoadFailed", { resource: title })
      )
    : resourcesError;

  return (
    <ResourceAssignmentPanel
      title={title}
      resources={resources}
      permissions={data?.permissions ?? []}
      editable={editable && !loadError}
      isLoading={isLoading || resourcesLoading}
      error={loadError}
      onRetry={() => {
        void mutate();
        onRetryResources?.();
      }}
      onSave={save}
    />
  );
}

interface ResourceWorkspaceProps {
  organizationId: string;
  targetType: TargetType;
  targetId: string;
  editable: boolean;
  onSaveComplete?: () => void | Promise<void>;
}

function AgentAccessWorkspace(props: ResourceWorkspaceProps) {
  const { t } = useTranslation();
  const { personas, isLoading, error, refresh } = usePersonaOptions();
  const resources = personas.map((persona) => ({
    id: String(persona.id),
    name: persona.name,
    description: persona.description,
  }));

  return (
    <ScopedResourcePanel
      {...props}
      resourceType="agent"
      title={t("admin.organizations.access.agents")}
      resources={resources}
      resourcesLoading={isLoading}
      resourcesError={
        error
          ? errorMessage(
              error,
              t("admin.organizations.access.resourceLoadFailed", {
                resource: t("admin.organizations.access.agents"),
              })
            )
          : undefined
      }
      onRetryResources={() => void refresh()}
    />
  );
}

function CollectionAccessWorkspace(props: ResourceWorkspaceProps) {
  const { t } = useTranslation();
  const { collections, isLoading, error, mutate } = useCollections();
  const resources = collections.map((collection) => ({
    id: collection.uuid,
    name: collection.name,
  }));

  return (
    <ScopedResourcePanel
      {...props}
      resourceType="rag_collection"
      title={t("admin.organizations.access.collections")}
      resources={resources}
      resourcesLoading={isLoading}
      resourcesError={
        error
          ? errorMessage(
              error,
              t("admin.organizations.access.resourceLoadFailed", {
                resource: t("admin.organizations.access.collections"),
              })
            )
          : undefined
      }
      onRetryResources={() => void mutate()}
    />
  );
}

export function OrganizationAccessPanel({
  organization,
  members,
  editable,
  resourceType,
  onSaveComplete,
}: OrganizationAccessPanelProps) {
  const { t } = useTranslation();
  const [targetType, setTargetType] = useState<TargetType>("organization");
  const activeMembers = useMemo(
    () => members.filter((member) => member.is_active !== false),
    [members]
  );
  const [selectedMemberId, setSelectedMemberId] = useState(
    activeMembers[0]?.user_id ?? ""
  );
  const effectiveSelectedMemberId = activeMembers.some(
    (member) => member.user_id === selectedMemberId
  )
    ? selectedMemberId
    : activeMembers[0]?.user_id ?? "";
  const targetId =
    targetType === "organization" ? organization.id : effectiveSelectedMemberId;
  return (
    <div className={cn("flex flex-col gap-4")}>
      <div className={cn("rounded-12 bg-background-neutral-01 p-1")}>
        <Tabs
          value={targetType}
          onValueChange={(value) => setTargetType(value as TargetType)}
        >
          <Tabs.List variant="contained">
            <Tabs.Trigger value="organization">
              {t("admin.organizations.access.unitAccess")}
            </Tabs.Trigger>
            <Tabs.Trigger value="user">
              {t("admin.organizations.access.memberAccess")}
            </Tabs.Trigger>
          </Tabs.List>
        </Tabs>
      </div>

      {targetType === "user" && (
        <div
          className={cn(
            "flex flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-4"
          )}
        >
          <Text mainUiAction text04 as="p">
            {t("admin.organizations.access.member")}
          </Text>
          {activeMembers.length === 0 ? (
            <Text text03 as="p">
              {t("admin.organizations.access.noActiveMembers")}
            </Text>
          ) : (
            <InputSelect
              value={effectiveSelectedMemberId}
              onValueChange={setSelectedMemberId}
            >
              <InputSelect.Trigger
                aria-label={t("admin.organizations.access.member")}
                placeholder={t("admin.organizations.access.selectMember")}
              />
              <InputSelect.Content>
                {activeMembers.map((member) => (
                  <InputSelect.Item key={member.user_id} value={member.user_id}>
                    {memberLabel(member)}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
          )}
        </div>
      )}

      {targetId ? (
        <div className={cn("grid gap-4")}>
          {resourceType !== "rag_collection" && (
            <AgentAccessWorkspace
              organizationId={organization.id}
              targetType={targetType}
              targetId={targetId}
              editable={editable}
              onSaveComplete={onSaveComplete}
            />
          )}
          {resourceType !== "agent" && (
            <CollectionAccessWorkspace
              organizationId={organization.id}
              targetType={targetType}
              targetId={targetId}
              editable={editable}
              onSaveComplete={onSaveComplete}
            />
          )}
        </div>
      ) : null}
    </div>
  );
}
