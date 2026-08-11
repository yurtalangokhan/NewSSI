"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { toast } from "@/hooks/useToast";
import { cn } from "@/lib/utils";

export type PermissionLevel = "read" | "execute" | "write" | "admin" | "owner";

export interface AssignableResource {
  id: string;
  name: string;
  description?: string;
}

export interface DirectResourcePermission {
  resource_id: string;
  resource_name: string;
  permission_level: PermissionLevel;
}

interface ResourceAssignmentPanelProps {
  title: string;
  resources: AssignableResource[];
  permissions: DirectResourcePermission[];
  editable: boolean;
  isLoading?: boolean;
  error?: string;
  onRetry?: () => void;
  onSave: (
    permissions: DirectResourcePermission[]
  ) => Promise<DirectResourcePermission[] | void>;
}

function toPermissionMap(permissions: DirectResourcePermission[]) {
  return new Map(
    permissions.map((permission) => [permission.resource_id, permission])
  );
}

function permissionSignature(permissions: DirectResourcePermission[]) {
  return JSON.stringify(
    permissions
      .map((permission) => ({
        resource_id: permission.resource_id,
        resource_name: permission.resource_name,
        permission_level: permission.permission_level,
      }))
      .sort((left, right) => left.resource_id.localeCompare(right.resource_id))
  );
}

function mapToPermissions(
  draft: Map<string, DirectResourcePermission>,
  resources: AssignableResource[]
) {
  const order = new Map(
    resources.map((resource, index) => [resource.id, index])
  );
  return Array.from(draft.values()).sort(
    (left, right) =>
      (order.get(left.resource_id) ?? Number.MAX_SAFE_INTEGER) -
      (order.get(right.resource_id) ?? Number.MAX_SAFE_INTEGER)
  );
}

export function ResourceAssignmentPanel({
  title,
  resources,
  permissions,
  editable,
  isLoading = false,
  error,
  onRetry,
  onSave,
}: ResourceAssignmentPanelProps) {
  const { t, i18n } = useTranslation();
  const incomingSignature = useMemo(
    () => permissionSignature(permissions),
    [permissions]
  );
  const [savedSignature, setSavedSignature] = useState(incomingSignature);
  const [draft, setDraft] = useState(() => toPermissionMap(permissions));
  const [query, setQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setDraft(toPermissionMap(permissions));
    setSavedSignature(incomingSignature);
  }, [incomingSignature, permissions]);

  const draftPermissions = useMemo(
    () => mapToPermissions(draft, resources),
    [draft, resources]
  );
  const isDirty = permissionSignature(draftPermissions) !== savedSignature;
  const normalizedQuery = query.trim().toLowerCase();
  const visibleResources = resources.filter((resource) => {
    if (selectedOnly && !draft.has(resource.id)) return false;
    if (!normalizedQuery) return true;
    return (
      resource.name.toLowerCase().includes(normalizedQuery) ||
      resource.description?.toLowerCase().includes(normalizedQuery)
    );
  });
  const allVisibleSelected =
    visibleResources.length > 0 &&
    visibleResources.every((resource) => draft.has(resource.id));
  const resourceLabel = title.toLocaleLowerCase(i18n.language);

  function toggleResource(resource: AssignableResource, checked: boolean) {
    setDraft((current) => {
      const next = new Map(current);
      if (checked) {
        next.set(resource.id, {
          resource_id: resource.id,
          resource_name: resource.name,
          permission_level: "read",
        });
      } else {
        next.delete(resource.id);
      }
      return next;
    });
  }

  function toggleAllVisible() {
    setDraft((current) => {
      const next = new Map(current);
      visibleResources.forEach((resource) => {
        if (allVisibleSelected) {
          next.delete(resource.id);
        } else if (!next.has(resource.id)) {
          next.set(resource.id, {
            resource_id: resource.id,
            resource_name: resource.name,
            permission_level: "read",
          });
        }
      });
      return next;
    });
  }

  async function handleSave() {
    setIsSaving(true);
    try {
      const saved = await onSave(draftPermissions);
      const nextPermissions = saved ?? draftPermissions;
      setDraft(toPermissionMap(nextPermissions));
      setSavedSignature(permissionSignature(nextPermissions));
      toast.success(
        t("admin.organizations.access.accessSaved", { resource: title })
      );
    } catch (saveError) {
      toast.error(
        saveError instanceof Error
          ? saveError.message
          : t("admin.organizations.access.accessSaveFailed", {
              resource: title,
            })
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-12 border border-border-01 bg-background-neutral-00 p-4"
      )}
    >
      <div className={cn("flex flex-wrap items-start justify-between gap-3")}>
        <div className={cn("flex flex-col gap-1")}>
          <Text headingH3 text04 as="p">
            {title}
          </Text>
          <Text secondaryBody text03 as="p">
            {t("admin.organizations.access.assignDescription", {
              resource: resourceLabel,
            })}
          </Text>
        </div>
        <div className={cn("flex items-center gap-2")}>
          <Text secondaryAction text03>
            {editable
              ? isDirty
                ? t("admin.organizations.designer.unsavedChanges")
                : t("admin.organizations.access.allChangesSaved")
              : t("admin.organizations.inspector.viewOnly")}
          </Text>
          <Button
            action
            primary
            size="md"
            disabled={!editable || !isDirty || isSaving}
            onClick={handleSave}
          >
            {isSaving
              ? t("admin.organizations.actions.saving")
              : t("admin.organizations.actions.saveChanges")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Text text03 as="p">
          {t("admin.organizations.access.loadingResources", {
            resource: resourceLabel,
          })}
        </Text>
      ) : error ? (
        <div
          className={cn(
            "flex items-center justify-between gap-3 rounded-08 border border-border-02 bg-background-neutral-01 p-3"
          )}
        >
          <Text text02 as="p">
            {error}
          </Text>
          {onRetry && (
            <Button secondary size="md" onClick={onRetry}>
              {t("admin.organizations.actions.tryAgain")}
            </Button>
          )}
        </div>
      ) : resources.length === 0 ? (
        <Text
          text03
          as="p"
          className={cn("rounded-08 bg-background-neutral-01 p-4 text-center")}
        >
          {t("admin.organizations.access.noResources", {
            resource: resourceLabel,
          })}
        </Text>
      ) : (
        <>
          <div className={cn("grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]")}>
            <InputTypeIn
              leftSearchIcon
              placeholder={t("admin.organizations.access.searchResources", {
                resource: resourceLabel,
              })}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <label
              className={cn(
                "flex items-center gap-2 rounded-08 border border-border-01 px-3 py-2"
              )}
            >
              <Checkbox
                checked={selectedOnly}
                onCheckedChange={setSelectedOnly}
                aria-label={t("admin.organizations.access.selectedOnly")}
              />
              <Text secondaryAction text02>
                {t("admin.organizations.access.selectedOnly")}
              </Text>
            </label>
          </div>

          <div
            className={cn(
              "flex items-center justify-between gap-3 border-b border-border-01 pb-3"
            )}
          >
            <Text secondaryBody text03>
              {t("admin.organizations.access.selectedCount", {
                count: draft.size,
              })}
            </Text>
            <Button
              tertiary
              size="md"
              disabled={!editable || visibleResources.length === 0}
              onClick={toggleAllVisible}
            >
              {allVisibleSelected
                ? t("admin.organizations.access.clearVisible")
                : t("admin.organizations.access.selectVisible")}
            </Button>
          </div>

          {visibleResources.length === 0 ? (
            <Text text03 as="p" className={cn("py-5 text-center")}>
              {t("admin.organizations.access.noFilterMatches", {
                resource: resourceLabel,
              })}
            </Text>
          ) : (
            <div className={cn("flex flex-col gap-2")}>
              {visibleResources.map((resource) => {
                const permission = draft.get(resource.id);
                return (
                  <div
                    key={resource.id}
                    className={cn(
                      "grid items-center gap-3 rounded-08 border p-3 md:grid-cols-[auto_minmax(0,1fr)_auto]",
                      permission
                        ? "border-border-03 bg-background-neutral-01"
                        : "border-border-01 bg-background-neutral-00"
                    )}
                  >
                    <Checkbox
                      checked={Boolean(permission)}
                      disabled={!editable}
                      onCheckedChange={(checked) =>
                        toggleResource(resource, checked)
                      }
                      aria-label={t(
                        "admin.organizations.access.selectResource",
                        {
                          name: resource.name,
                        }
                      )}
                    />
                    <div className={cn("min-w-0")}>
                      <Text
                        mainUiAction
                        text04
                        as="p"
                        className={cn("truncate")}
                      >
                        {resource.name}
                      </Text>
                      {resource.description && (
                        <Text
                          secondaryBody
                          text03
                          as="p"
                          className={cn("truncate")}
                        >
                          {resource.description}
                        </Text>
                      )}
                    </div>
                    {permission ? (
                      <Text secondaryBody text03>
                        {t("admin.organizations.access.assigned")}
                      </Text>
                    ) : (
                      <Text secondaryBody text03>
                        {t("admin.organizations.access.notAssigned")}
                      </Text>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
