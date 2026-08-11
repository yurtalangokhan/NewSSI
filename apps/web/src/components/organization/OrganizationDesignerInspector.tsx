"use client";

import { useMemo, useState } from "react";

import { OrganizationAccessPanel } from "@/components/organization/OrganizationAccessPanel";
import type {
  CreateOrganization,
  DeleteOrganization,
  MoveOrganization,
  OrganizationMember,
  OrganizationNode,
  UpdateOrganization,
} from "@/components/organization/organizationTypes";
import { OrganizationUserAssignmentsPanel } from "@/components/organization/OrganizationUserAssignmentsPanel";
import { SvgOrganization, SvgShield, SvgUsers } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationDesignerInspectorProps {
  organization: OrganizationNode | null;
  organizations: OrganizationNode[];
  members: OrganizationMember[];
  editable: boolean;
  capabilityLoading: boolean;
  mobileOpen?: boolean;
  onBackToMap?: () => void;
  onAccessSaveComplete?: () => void | Promise<void>;
  onCreateOrg: CreateOrganization;
  onUpdateOrg: UpdateOrganization;
  onDeleteOrg: DeleteOrganization;
  onMoveOrg: MoveOrganization;
  onAddUser: (userId: string, role: string) => Promise<void>;
  onRoleChange: (userId: string, role: string) => Promise<void>;
  onRemoveUser: (userId: string) => Promise<void>;
}

function collectDescendantIds(organization: OrganizationNode) {
  const ids = new Set<string>();
  function visit(node: OrganizationNode) {
    for (const child of node.children ?? []) {
      ids.add(child.id);
      visit(child);
    }
  }
  visit(organization);
  return ids;
}

function flattenOrganizations(organizations: OrganizationNode[]) {
  const flattened: OrganizationNode[] = [];
  function visit(organization: OrganizationNode) {
    flattened.push(organization);
    (organization.children ?? []).forEach(visit);
  }
  organizations.forEach(visit);
  return flattened;
}

export function OrganizationDesignerInspector({
  organization,
  organizations,
  members,
  editable,
  capabilityLoading,
  mobileOpen = true,
  onBackToMap,
  onAccessSaveComplete,
  onCreateOrg,
  onUpdateOrg,
  onDeleteOrg,
  onMoveOrg,
  onAddUser,
  onRoleChange,
  onRemoveUser,
}: OrganizationDesignerInspectorProps) {
  const [activeTab, setActiveTab] = useState("details");
  const [name, setName] = useState(organization?.name ?? "");

  const moveTargets = useMemo(() => {
    if (!organization) return [];
    const excluded = collectDescendantIds(organization);
    excluded.add(organization.id);
    return flattenOrganizations(organizations).filter(
      (candidate) => !excluded.has(candidate.id)
    );
  }, [organization, organizations]);
  const canMutate = editable && !capabilityLoading;

  return (
    <aside
      aria-label="Organization inspector"
      data-mobile-open={mobileOpen}
      className={cn(
        "absolute inset-0 z-10 flex min-h-0 flex-col border-l border-border-02 bg-background-neutral-00",
        (!organization || !mobileOpen) && "max-md:hidden",
        "md:static md:w-[26rem] md:shrink-0"
      )}
    >
      {!organization ? (
        <div
          className={cn(
            "flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center"
          )}
        >
          <SvgOrganization className={cn("h-10 w-10 stroke-text-02")} />
          <Text headingH3 text03 as="p">
            Select an organization
          </Text>
          <Text secondaryBody text03 as="p">
            Choose a node to inspect its details, users, and access.
          </Text>
        </div>
      ) : (
        <>
          <header className={cn("border-b border-border-02 px-5 pt-5")}>
            {onBackToMap && (
              <Button
                secondary
                size="md"
                className={cn("mb-4 md:hidden")}
                onClick={onBackToMap}
              >
                Back to map
              </Button>
            )}
            <div className={cn("mb-4 flex min-w-0 items-start gap-3")}>
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-08 bg-background-neutral-03"
                )}
              >
                <SvgOrganization className={cn("h-4 w-4 stroke-text-03")} />
              </div>
              <div className={cn("min-w-0 flex-1")}>
                <Text headingH3 text04 as="p" className={cn("truncate")}>
                  {organization.name}
                </Text>
                <Text secondaryBody text03 as="p" className={cn("truncate")}>
                  {organization.path}
                </Text>
              </div>
              <Text secondaryMono text03>
                {capabilityLoading
                  ? "Checking access…"
                  : canMutate
                    ? "Editable"
                    : "View only"}
              </Text>
            </div>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <Tabs.List variant="pill">
                <Tabs.Trigger value="details" icon={SvgOrganization}>
                  Details
                </Tabs.Trigger>
                <Tabs.Trigger value="users" icon={SvgUsers}>
                  Users
                </Tabs.Trigger>
                <Tabs.Trigger value="access" icon={SvgShield}>
                  Access
                </Tabs.Trigger>
              </Tabs.List>
            </Tabs>
          </header>

          <div className={cn("min-h-0 flex-1 overflow-y-auto p-5")}>
            {activeTab === "details" ? (
              <div className={cn("flex flex-col gap-5")}>
                <div className={cn("flex flex-col gap-2")}>
                  <Text secondaryAction text03>
                    Organization name
                  </Text>
                  <InputTypeIn
                    aria-label="Organization name"
                    value={name}
                    variant={canMutate ? "primary" : "disabled"}
                    onChange={(event) => setName(event.target.value)}
                  />
                  <Button
                    action
                    primary
                    size="md"
                    disabled={!canMutate || !name.trim() || name === organization.name}
                    onClick={() =>
                      void onUpdateOrg(organization.id, { name: name.trim() })
                    }
                  >
                    Save details
                  </Button>
                </div>

                <div
                  className={cn(
                    "grid grid-cols-2 gap-3 border-y border-border-01 py-4"
                  )}
                >
                  <div>
                    <Text figureSmallValue text04 as="p">
                      {members.length}
                    </Text>
                    <Text figureSmallLabel text03>
                      Active members
                    </Text>
                  </div>
                  <div>
                    <Text figureSmallValue text04 as="p">
                      {organization.permission_count ?? 0}
                    </Text>
                    <Text figureSmallLabel text03>
                      Direct grants
                    </Text>
                  </div>
                </div>

                <div className={cn("flex flex-col gap-2")}>
                  <Text secondaryAction text03>
                    Hierarchy
                  </Text>
                  <Button
                    secondary
                    size="md"
                    disabled={!canMutate}
                    onClick={() => {
                      const childName = window.prompt("Enter organization name:");
                      if (childName?.trim()) {
                        void onCreateOrg(organization.id, childName.trim());
                      }
                    }}
                  >
                    Add child
                  </Button>
                  <InputSelect
                    value={organization.parent_id ?? ""}
                    disabled={!canMutate || organization.parent_id === null}
                    onValueChange={(parentId) =>
                      void onMoveOrg(organization.id, parentId)
                    }
                  >
                    <InputSelect.Trigger
                      aria-label="Move to"
                      placeholder="Move to…"
                    />
                    <InputSelect.Content>
                      {moveTargets.map((target) => (
                        <InputSelect.Item key={target.id} value={target.id}>
                          {target.name}
                        </InputSelect.Item>
                      ))}
                    </InputSelect.Content>
                  </InputSelect>
                </div>

                <div className={cn("border-t border-border-01 pt-5")}>
                  <Button
                    danger
                    secondary
                    size="md"
                    disabled={!canMutate}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete "${organization.name}"?`
                        )
                      ) {
                        void onDeleteOrg(organization.id);
                      }
                    }}
                  >
                    Delete organization
                  </Button>
                </div>
              </div>
            ) : activeTab === "users" ? (
              <OrganizationUserAssignmentsPanel
                assignments={members}
                onAdd={onAddUser}
                onRoleChange={onRoleChange}
                onRemove={onRemoveUser}
                editable={canMutate}
              />
            ) : (
              <OrganizationAccessPanel
                organization={organization}
                members={members}
                editable={canMutate}
                onSaveComplete={onAccessSaveComplete}
              />
            )}
          </div>
        </>
      )}
    </aside>
  );
}
