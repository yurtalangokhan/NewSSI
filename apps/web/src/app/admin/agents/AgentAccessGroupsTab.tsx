"use client";

import useSWR from "swr";
import { useMemo, useState } from "react";
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

export default function AgentAccessGroupsTab({
  agents,
}: AgentAccessGroupsTabProps) {
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

  const { data: usersResponse } = useSWR<UsersResponse>(
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
      toast.error("Group name is required");
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
      toast.success("Agent group saved");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to save agent group"
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
      toast.success("Agent group deleted");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to delete agent group"
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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <Text as="p" headingH3>
            Access groups
          </Text>
          {isAdmin && (
            <Button onClick={startNewGroup} disabled={isSaving}>
              New
            </Button>
          )}
        </div>

        <InputTypeIn
          value={groupSearch}
          placeholder="Search groups..."
          onChange={(event) => setGroupSearch(event.target.value)}
          leftSearchIcon
        />

        {isGroupsLoading ? (
          <Card>
            <Text as="p">Loading groups...</Text>
          </Card>
        ) : groups.length === 0 && !draft ? (
          <Card variant="tertiary">
            <Text as="p">No access groups yet.</Text>
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
                  {group.user_ids.length} users, {group.persona_ids.length}{" "}
                  agents
                </Text>
              </Card>
            ))}
            {visibleGroups.length === 0 && (
              <Card variant="tertiary">
                <Text as="p">No groups match this search.</Text>
              </Card>
            )}
          </div>
        )}
      </div>

      <Card>
        {!editableDraft ? (
          <div className="flex flex-col gap-2">
            <Text as="p" headingH3>
              Select a group
            </Text>
            <Text as="p" secondaryBody text03>
              Agent access groups let admins decide which users can use a set of
              agents.
            </Text>
          </div>
        ) : (
          <div className="flex flex-col gap-5 w-full">
            {!isAdmin && (
              <Card variant="tertiary">
                <Text as="p">Only admins can change agent access groups.</Text>
              </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
              <div className="flex flex-col gap-2">
                <Text as="p" secondaryBody>
                  Group name
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
                  Description
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
                      Users
                    </Text>
                    <Text as="p" text03 secondaryBody>
                      {editableDraft.user_ids.length} selected from{" "}
                      {users.length}
                    </Text>
                  </div>
                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={showSelectedUsersOnly}
                      onCheckedChange={setShowSelectedUsersOnly}
                    />
                    <Text as="span" secondaryBody>
                      Selected
                    </Text>
                  </label>
                </div>
                <InputTypeIn
                  value={userSearch}
                  placeholder="Filter users by email or role..."
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
                      <Text as="p">No users match the current filters.</Text>
                    </Card>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <Text as="p" mainUiBody>
                      Agents
                    </Text>
                    <Text as="p" text03 secondaryBody>
                      {editableDraft.persona_ids.length} selected from{" "}
                      {customAgents.length}
                    </Text>
                  </div>
                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={showSelectedAgentsOnly}
                      onCheckedChange={setShowSelectedAgentsOnly}
                    />
                    <Text as="span" secondaryBody>
                      Selected
                    </Text>
                  </label>
                </div>
                <InputTypeIn
                  value={agentSearch}
                  placeholder="Filter agents by name, owner, or description..."
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
                          {agent.owner?.email ?? "System"}
                        </Text>
                      </span>
                    </label>
                  ))}
                  {visibleAgents.length === 0 && (
                    <Card variant="tertiary">
                      <Text as="p">No agents match the current filters.</Text>
                    </Card>
                  )}
                </div>
              </div>
            </div>

            {isAdmin && (
              <div className="flex justify-end gap-2">
                {editableDraft.id > 0 && (
                  <Button secondary onClick={deleteGroup} disabled={isSaving}>
                    Delete
                  </Button>
                )}
                <Button onClick={saveGroup} disabled={isSaving}>
                  Save changes
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
