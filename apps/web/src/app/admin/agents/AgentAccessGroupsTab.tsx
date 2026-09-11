"use client";

import useSWR from "swr";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import { authenticatedFetch, errorHandlingFetcher } from "@/lib/fetcher";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { User } from "@/lib/types";
import { useUser } from "@/providers/UserProvider";
import Card from "@/refresh-components/cards/Card";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";

interface AgentGroup {
  id: number;
  name: string;
  description: string;
  user_ids: string[];
  persona_ids: number[];
}

interface UsersResponse {
  items?: User[];
  users?: User[];
}

interface AgentAccessGroupsTabProps {
  agents: MinimalPersonaSnapshot[];
}

const AGENT_GROUPS_API_PATH = "/api/agent-groups";

function toggleString(values: string[], value: string, enabled: boolean) {
  return enabled
    ? Array.from(new Set([...values, value]))
    : values.filter((item) => item !== value);
}

function toggleNumber(values: number[], value: number, enabled: boolean) {
  return enabled
    ? Array.from(new Set([...values, value]))
    : values.filter((item) => item !== value);
}

export function AgentAccessGroupsSkeleton() {
  return (
    <div
      className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 w-full"
      data-testid="admin-agents-access-groups-skeleton"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="h-6 w-32 rounded-06 bg-background-neutral-03 animate-pulse" />
          <div className="h-8 w-20 rounded-08 bg-background-neutral-02 animate-pulse" />
        </div>

        <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-00 flex items-center px-3 gap-2">
          <div className="h-4 w-4 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          <div className="h-4 w-40 rounded bg-background-tint-04 animate-pulse" />
        </div>

        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} variant="secondary">
              <div className="space-y-2 py-1">
                <div className="h-4 w-3/4 rounded bg-background-neutral-03 animate-pulse" />
                <div className="h-3 w-1/2 rounded bg-background-neutral-02 animate-pulse" />
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card>
        <div className="flex flex-col gap-5 w-full">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
            <div className="space-y-2">
              <div className="h-4 w-24 rounded bg-background-neutral-03 animate-pulse" />
              <div className="h-10 w-full rounded-08 bg-background-neutral-02 animate-pulse" />
            </div>
            <div className="space-y-2">
              <div className="h-4 w-24 rounded bg-background-neutral-03 animate-pulse" />
              <div className="h-16 w-full rounded-08 bg-background-neutral-02 animate-pulse" />
            </div>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 w-full">
            <div className="space-y-3 rounded-08 border border-border-01 p-3">
              <div className="h-4 w-28 rounded bg-background-neutral-03 animate-pulse" />
              <div className="h-9 w-full rounded-08 bg-background-neutral-02 animate-pulse" />
              <div className="space-y-2 pt-1">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-8 w-full rounded-06 bg-background-neutral-02/60 animate-pulse"
                  />
                ))}
              </div>
            </div>
            <div className="space-y-3 rounded-08 border border-border-01 p-3">
              <div className="h-4 w-28 rounded bg-background-neutral-03 animate-pulse" />
              <div className="h-9 w-full rounded-08 bg-background-neutral-02 animate-pulse" />
              <div className="space-y-2 pt-1">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-8 w-full rounded-06 bg-background-neutral-02/60 animate-pulse"
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function AgentAccessGroupsTab({
  agents,
}: AgentAccessGroupsTabProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.agentAccessGroups",
  });
  const { isAdmin } = useUser();
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [draft, setDraft] = useState<AgentGroup | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [groupSearch, setGroupSearch] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [agentSearch, setAgentSearch] = useState("");
  const [showSelectedUsersOnly, setShowSelectedUsersOnly] = useState(false);
  const [showSelectedAgentsOnly, setShowSelectedAgentsOnly] = useState(false);

  const {
    data: groups = [],
    mutate: refreshGroups,
    isLoading: isGroupsLoading,
  } = useSWR<AgentGroup[]>(AGENT_GROUPS_API_PATH, errorHandlingFetcher);

  const { data: usersResponse, isLoading: isUsersLoading } =
    useSWR<UsersResponse>(
      "/api/user-service/users/?limit=1000",
      errorHandlingFetcher
    );

  const users = useMemo(
    () => usersResponse?.items ?? usersResponse?.users ?? [],
    [usersResponse]
  );

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedGroupId) ?? null,
    [groups, selectedGroupId]
  );

  const editableDraft = draft ?? selectedGroup;
  const customAgents = agents.filter(
    (agent) => !agent.builtin_persona && typeof agent.id === "number"
  );
  const visibleGroups = useMemo(() => {
    const query = groupSearch.trim().toLowerCase();
    if (!query) return groups;
    return groups.filter(
      (group) =>
        group.name.toLowerCase().includes(query) ||
        group.description.toLowerCase().includes(query)
    );
  }, [groups, groupSearch]);
  const visibleUsers = useMemo(() => {
    const query = userSearch.trim().toLowerCase();
    return users.filter((user) => {
      const matchesQuery =
        !query ||
        user.email.toLowerCase().includes(query) ||
        user.role.toLowerCase().includes(query);
      const matchesSelected =
        !showSelectedUsersOnly || editableDraft?.user_ids.includes(user.id);
      return matchesQuery && matchesSelected;
    });
  }, [editableDraft?.user_ids, showSelectedUsersOnly, userSearch, users]);
  const visibleAgents = useMemo(() => {
    const query = agentSearch.trim().toLowerCase();
    return customAgents.filter((agent) => {
      const matchesQuery =
        !query ||
        agent.name.toLowerCase().includes(query) ||
        agent.description.toLowerCase().includes(query) ||
        (agent.owner?.email ?? "").toLowerCase().includes(query);
      const matchesSelected =
        !showSelectedAgentsOnly ||
        editableDraft?.persona_ids.includes(agent.id);
      return matchesQuery && matchesSelected;
    });
  }, [
    agentSearch,
    customAgents,
    editableDraft?.persona_ids,
    showSelectedAgentsOnly,
  ]);

  async function saveGroup() {
    if (!editableDraft || !editableDraft.name.trim()) {
      toast.error(t("groupNameRequired"));
      return;
    }

    setIsSaving(true);
    try {
      const isExisting = editableDraft.id > 0;
      const response = await authenticatedFetch(
        isExisting
          ? `${AGENT_GROUPS_API_PATH}/${editableDraft.id}`
          : AGENT_GROUPS_API_PATH,
        {
          method: isExisting ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: editableDraft.name.trim(),
            description: editableDraft.description.trim(),
            user_ids: editableDraft.user_ids,
            persona_ids: editableDraft.persona_ids,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const saved = (await response.json()) as AgentGroup;
      await refreshGroups();
      setSelectedGroupId(saved.id);
      setDraft(null);
      toast.success(t("toastSaved"));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("toastSaveFailed")
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteGroup() {
    if (!editableDraft || editableDraft.id <= 0) return;

    setIsSaving(true);
    try {
      const response = await authenticatedFetch(
        `${AGENT_GROUPS_API_PATH}/${editableDraft.id}`,
        {
          method: "DELETE",
        }
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await refreshGroups();
      setSelectedGroupId(null);
      setDraft(null);
      toast.success(t("toastDeleted"));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("toastDeleteFailed")
      );
    } finally {
      setIsSaving(false);
    }
  }

  function startNewGroup() {
    setSelectedGroupId(null);
    setDraft({
      id: -Date.now(),
      name: "",
      description: "",
      user_ids: [],
      persona_ids: [],
    });
  }

  function updateDraft(updater: (group: AgentGroup) => AgentGroup) {
    const base = editableDraft ?? {
      id: -Date.now(),
      name: "",
      description: "",
      user_ids: [],
      persona_ids: [],
    };
    setDraft(updater(base));
  }

  if (isGroupsLoading) {
    return <AgentAccessGroupsSkeleton />;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <Text as="p" headingH3>
            {t("title")}
          </Text>
          {isAdmin && (
            <Button onClick={startNewGroup} disabled={isSaving}>
              {t("newButton")}
            </Button>
          )}
        </div>

        <InputTypeIn
          value={groupSearch}
          placeholder={t("searchGroupsPlaceholder")}
          onChange={(event) => setGroupSearch(event.target.value)}
          leftSearchIcon
        />

        {isGroupsLoading ? (
          <Card>
            <Text as="p">{t("loadingGroups")}</Text>
          </Card>
        ) : groups.length === 0 && !draft ? (
          <Card variant="tertiary">
            <Text as="p">{t("noGroupsYet")}</Text>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {visibleGroups.map((group) => (
              <Card
                key={group.id}
                variant={group.id === selectedGroupId ? "primary" : "secondary"}
                className="cursor-pointer"
                onClick={() => {
                  setSelectedGroupId(group.id);
                  setDraft(null);
                }}
              >
                <Text as="p" mainUiBody>
                  {group.name}
                </Text>
                <Text as="p" text03 secondaryBody>
                  {t("groupMemberSummary", {
                    userCount: group.user_ids.length,
                    agentCount: group.persona_ids.length,
                  })}
                </Text>
              </Card>
            ))}
            {visibleGroups.length === 0 && (
              <Card variant="tertiary">
                <Text as="p">{t("noGroupsMatchSearch")}</Text>
              </Card>
            )}
          </div>
        )}
      </div>

      <Card>
        {!editableDraft ? (
          <div className="flex flex-col gap-2">
            <Text as="p" headingH3>
              {t("selectGroupTitle")}
            </Text>
            <Text as="p" secondaryBody text03>
              {t("selectGroupDescription")}
            </Text>
          </div>
        ) : (
          <div className="flex flex-col gap-5 w-full">
            {!isAdmin && (
              <Card variant="tertiary">
                <Text as="p">{t("adminOnlyNotice")}</Text>
              </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
              <div className="flex flex-col gap-2">
                <Text as="p" secondaryBody>
                  {t("groupNameLabel")}
                </Text>
                <InputTypeIn
                  value={editableDraft.name}
                  readOnly={!isAdmin}
                  onChange={(event) =>
                    updateDraft((group) => ({
                      ...group,
                      name: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Text as="p" secondaryBody>
                  {t("descriptionLabel")}
                </Text>
                <InputTextArea
                  rows={2}
                  value={editableDraft.description}
                  readOnly={!isAdmin}
                  onChange={(event) =>
                    updateDraft((group) => ({
                      ...group,
                      description: event.target.value,
                    }))
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 w-full">
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <Text as="p" mainUiBody>
                      {t("usersTitle")}
                    </Text>
                    <Text as="p" text03 secondaryBody>
                      {t("selectedFromTotal", {
                        selected: editableDraft.user_ids.length,
                        total: users.length,
                      })}
                    </Text>
                  </div>
                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={showSelectedUsersOnly}
                      onCheckedChange={setShowSelectedUsersOnly}
                    />
                    <Text as="span" secondaryBody>
                      {t("selectedLabel")}
                    </Text>
                  </label>
                </div>
                <InputTypeIn
                  value={userSearch}
                  placeholder={t("filterUsersPlaceholder")}
                  onChange={(event) => setUserSearch(event.target.value)}
                  leftSearchIcon
                />
                <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-1">
                  {visibleUsers.map((user) => (
                    <label
                      key={user.id}
                      className="flex items-center gap-2 p-2 border border-border-01 rounded-08"
                    >
                      <Checkbox
                        checked={editableDraft.user_ids.includes(user.id)}
                        disabled={!isAdmin}
                        onCheckedChange={(checked) =>
                          updateDraft((group) => ({
                            ...group,
                            user_ids: toggleString(
                              group.user_ids,
                              user.id,
                              checked
                            ),
                          }))
                        }
                      />
                      <span className="min-w-0">
                        <Text as="span" mainUiBody>
                          {user.email}
                        </Text>
                        <Text as="span" text03 secondaryBody>
                          {user.role}
                        </Text>
                      </span>
                    </label>
                  ))}
                  {visibleUsers.length === 0 && (
                    <Card variant="tertiary">
                      <Text as="p">{t("noUsersMatch")}</Text>
                    </Card>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <Text as="p" mainUiBody>
                      {t("agentsTitle")}
                    </Text>
                    <Text as="p" text03 secondaryBody>
                      {t("selectedFromTotal", {
                        selected: editableDraft.persona_ids.length,
                        total: customAgents.length,
                      })}
                    </Text>
                  </div>
                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={showSelectedAgentsOnly}
                      onCheckedChange={setShowSelectedAgentsOnly}
                    />
                    <Text as="span" secondaryBody>
                      {t("selectedLabel")}
                    </Text>
                  </label>
                </div>
                <InputTypeIn
                  value={agentSearch}
                  placeholder={t("filterAgentsPlaceholder")}
                  onChange={(event) => setAgentSearch(event.target.value)}
                  leftSearchIcon
                />
                <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-1">
                  {visibleAgents.map((agent) => (
                    <label
                      key={agent.id}
                      className="flex items-start gap-2 p-2 border border-border-01 rounded-08"
                    >
                      <Checkbox
                        checked={editableDraft.persona_ids.includes(agent.id)}
                        disabled={!isAdmin}
                        onCheckedChange={(checked) =>
                          updateDraft((group) => ({
                            ...group,
                            persona_ids: toggleNumber(
                              group.persona_ids,
                              agent.id,
                              checked
                            ),
                          }))
                        }
                      />
                      <span className="min-w-0 flex flex-col gap-1">
                        <Text as="span" mainUiBody>
                          {agent.name}
                        </Text>
                        <Text as="span" text03 secondaryBody>
                          {agent.owner?.email ?? t("systemOwner")}
                        </Text>
                      </span>
                    </label>
                  ))}
                  {visibleAgents.length === 0 && (
                    <Card variant="tertiary">
                      <Text as="p">{t("noAgentsMatch")}</Text>
                    </Card>
                  )}
                </div>
              </div>
            </div>

            {isAdmin && (
              <div className="flex justify-end gap-2">
                {editableDraft.id > 0 && (
                  <Button secondary onClick={deleteGroup} disabled={isSaving}>
                    {t("deleteButton")}
                  </Button>
                )}
                <Button onClick={saveGroup} disabled={isSaving}>
                  {t("saveChangesButton")}
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
