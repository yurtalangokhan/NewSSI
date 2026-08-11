"use client";

import { useMemo, useState } from "react";
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
  onSaveComplete?: () => void | Promise<void>;
}

interface ScopedPermissionsResponse {
  permissions: DirectResourcePermission[];
  count: number;
}

type TargetType = "organization" | "user";
type ResourceType = "agent" | "rag_collection";

async function readErrorDetail(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;
  return data?.detail || data?.message || fallback;
}

async function permissionFetcher(url: string): Promise<ScopedPermissionsResponse> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Direct permissions could not be loaded"));
  }
  return response.json();
}

function memberLabel(member: OrganizationAccessMember) {
  const fullName = [member.user?.first_name, member.user?.last_name]
    .filter(Boolean)
    .join(" ");
  return fullName || member.user?.email || member.user?.username || member.user_id;
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
  const endpoint = `/api/user-service/permissions/organizations/${organizationId}/targets/${targetType}/${targetId}/resources/${resourceType}`;
  const { data, error, isLoading, mutate } = useSWR<ScopedPermissionsResponse>(
    endpoint,
    permissionFetcher
  );

  async function save(permissions: DirectResourcePermission[]) {
    const response = await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permissions }),
    });
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, `${title} access could not be saved`));
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
    ? errorMessage(error, `${title} access could not be loaded`)
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

export function OrganizationAccessPanel({
  organization,
  members,
  editable,
  onSaveComplete,
}: OrganizationAccessPanelProps) {
  const [targetType, setTargetType] = useState<TargetType>("organization");
  const activeMembers = useMemo(
    () => members.filter((member) => member.is_active !== false),
    [members]
  );
  const [selectedMemberId, setSelectedMemberId] = useState(
    activeMembers[0]?.user_id ?? ""
  );
  const { personas, isLoading: agentsLoading, error: agentsError, refresh } =
    usePersonaOptions();
  const {
    collections,
    isLoading: collectionsLoading,
    error: collectionsError,
    mutate: refreshCollections,
  } = useCollections();

  const effectiveSelectedMemberId = activeMembers.some(
    (member) => member.user_id === selectedMemberId
  )
    ? selectedMemberId
    : (activeMembers[0]?.user_id ?? "");
  const targetId =
    targetType === "organization" ? organization.id : effectiveSelectedMemberId;
  const agentResources = personas.map((persona) => ({
    id: String(persona.id),
    name: persona.name,
    description: persona.description,
  }));
  const collectionResources = collections.map((collection) => ({
    id: collection.uuid,
    name: collection.name,
  }));

  return (
    <div className={cn("flex flex-col gap-4")}>
      <div className={cn("rounded-12 bg-background-neutral-01 p-1")}>
        <Tabs value={targetType} onValueChange={(value) => setTargetType(value as TargetType)}>
          <Tabs.List variant="contained">
            <Tabs.Trigger value="organization">Unit access</Tabs.Trigger>
            <Tabs.Trigger value="user">Member access</Tabs.Trigger>
          </Tabs.List>
        </Tabs>
      </div>

      {targetType === "user" && (
        <div className={cn("flex flex-col gap-2 rounded-12 border border-border-01 bg-background-neutral-00 p-4")}>
          <Text mainUiAction text04 as="p">
            Member
          </Text>
          {activeMembers.length === 0 ? (
            <Text text03 as="p">
              Add an active member to this unit before assigning individual access.
            </Text>
          ) : (
            <InputSelect
              value={effectiveSelectedMemberId}
              onValueChange={setSelectedMemberId}
            >
              <InputSelect.Trigger aria-label="Member" placeholder="Select a member" />
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
        <div className={cn("grid gap-4 xl:grid-cols-2")}>
          <ScopedResourcePanel
            organizationId={organization.id}
            targetType={targetType}
            targetId={targetId}
            resourceType="agent"
            title="Agents"
            resources={agentResources}
            editable={editable}
            resourcesLoading={agentsLoading}
            resourcesError={
              agentsError ? errorMessage(agentsError, "Agents could not be loaded") : undefined
            }
            onRetryResources={() => void refresh()}
            onSaveComplete={onSaveComplete}
          />
          <ScopedResourcePanel
            organizationId={organization.id}
            targetType={targetType}
            targetId={targetId}
            resourceType="rag_collection"
            title="Collections"
            resources={collectionResources}
            editable={editable}
            resourcesLoading={collectionsLoading}
            resourcesError={
              collectionsError
                ? errorMessage(collectionsError, "Collections could not be loaded")
                : undefined
            }
            onRetryResources={() => void refreshCollections()}
            onSaveComplete={onSaveComplete}
          />
        </div>
      ) : null}
    </div>
  );
}
