"use client";

import { useMemo, useCallback, useState } from "react";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import type { FullPersona } from "@/app/admin/agents/interfaces";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import AgentAvailabilityBadge from "@/refresh-components/agents/AgentAvailabilityBadge";
import Button from "@/refresh-components/buttons/Button";
import { useAppRouter } from "@/hooks/appNavigation";
import IconButton from "@/refresh-components/buttons/IconButton";
import { usePinnedAgents, useAgent, useAgents } from "@/hooks/useAgents";
import { cn, noProp } from "@/lib/utils";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import {
  checkUserOwnsAgent,
  updateAgentSharedStatus,
  updateAgentFeaturedStatus,
  deleteAgent,
} from "@/lib/agents";
import { useUser } from "@/providers/UserProvider";
import {
  SvgActions,
  SvgBarChart,
  SvgBubbleText,
  SvgEdit,
  SvgPin,
  SvgPinned,
  SvgShare,
  SvgTrash,
  SvgUser,
} from "@opal/icons";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import ShareAgentModal from "@/sections/modals/ShareAgentModal";
import AgentViewerModal from "@/sections/modals/AgentViewerModal";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import { toast } from "@/hooks/useToast";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Content } from "@opal/layouts";
import { Interactive } from "@opal/core";
import { Card } from "@/refresh-components/cards";
import { useTranslation } from "react-i18next";

export interface AgentCardProps {
  agent: MinimalPersonaSnapshot;
}

export default function AgentCard({ agent }: AgentCardProps) {
  const route = useAppRouter();
  const { t } = useTranslation();
  const router = useRouter();
  const { pinnedAgents, togglePinnedAgent } = usePinnedAgents();
  const { refresh: refreshAgents } = useAgents();
  const isDynamicAgent = !!agent.external_id || !!agent.is_dynamic;
  const routeAgentId = agent.external_id ?? agent.id;
  const pinned = useMemo(
    () => pinnedAgents.some((pinnedAgent) => String(pinnedAgent.id) === String(agent.id)),
    [agent.id, pinnedAgents]
  );
  const { user, isAdmin, isCurator } = useUser();
  const isPaidEnterpriseFeaturesEnabled = usePaidEnterpriseFeaturesEnabled();
  const canUpdateFeaturedStatus = isAdmin || isCurator;
  const isOwnedByUser = checkUserOwnsAgent(user, agent);
  const ownerEmail = useMemo(() => {
    if (agent.owner?.id && user?.id && agent.owner.id === user.id) {
      return user.email;
    }
    return agent.owner?.email || "Onyx";
  }, [agent.owner?.email, agent.owner?.id, user?.email, user?.id]);
  const canEdit = isOwnedByUser || isAdmin;
  const shareAgentModal = useCreateModal();
  const agentViewerModal = useCreateModal();
  const { agent: fullAgent, refresh: refreshAgent } = useAgent(agent.external_id ?? agent.id);
  const agentForViewer = useMemo<FullPersona>(
    () =>
      fullAgent ?? {
        ...agent,
        users: [],
        groups: [],
        document_sets: [],
        hierarchy_nodes: [],
        user_file_ids: [],
        starter_messages: null,
        system_prompt: "",
        replace_base_system_prompt: false,
        task_prompt: "",
        datetime_aware: true,
        mcp_tools: [],
        rag_config: {
          document_processing: [],
          knowledge_graph: [],
        },
        attached_documents: [],
        search_start_date: null,
      },
    [fullAgent, agent]
  );

  // Start chat and auto-pin unpinned agents to the sidebar
  const handleStartChat = useCallback(() => {
    if (!pinned && !isDynamicAgent) {
      togglePinnedAgent(agent, true);
    }
    route({ agentId: routeAgentId });
  }, [pinned, isDynamicAgent, togglePinnedAgent, agent, route, routeAgentId]);

  const handleShare = useCallback(
    async (
      userIds: string[],
      groupIds: number[],
      isPublic: boolean,
      isFeatured: boolean,
      labelIds: number[]
    ) => {
      const shareError = await updateAgentSharedStatus(
        agent.id,
        userIds,
        groupIds,
        isPublic,
        isPaidEnterpriseFeaturesEnabled,
        labelIds
      );

      if (shareError) {
        toast.error(`Failed to share agent: ${shareError}`);
        return;
      }

      if (canUpdateFeaturedStatus) {
        const featuredError = await updateAgentFeaturedStatus(
          agent.id,
          isFeatured
        );
        if (featuredError) {
          toast.error(`Failed to update featured status: ${featuredError}`);
          refreshAgent();
          return;
        }
      }

      refreshAgent();
      shareAgentModal.toggle(false);
    },
    [
      agent.id,
      canUpdateFeaturedStatus,
      isPaidEnterpriseFeaturesEnabled,
      refreshAgent,
    ]
  );

  const deleteModal = useCreateModal();
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = useCallback(async () => {
    setIsDeleting(true);
    try {
      const error = await deleteAgent(agent.external_id ?? agent.id);
      if (error) {
        toast.error(`Failed to delete agent: ${error}`);
      } else {
        toast.success(`Agent "${agent.name}" deleted.`);
        await refreshAgents();
      }
    } finally {
      setIsDeleting(false);
      deleteModal.toggle(false);
    }
  }, [agent.id, agent.name, refreshAgents, deleteModal]);

  const actionCount =
    agent.tools.length > 0 ? agent.tools.length : (agent.mcp_tools?.length ?? 0);

  return (
    <>
      <shareAgentModal.Provider>
        <ShareAgentModal
          agentId={agent.id}
          userIds={fullAgent?.users?.map((u) => u.id) ?? []}
          groupIds={fullAgent?.groups ?? []}
          isPublic={fullAgent?.is_public ?? false}
          isFeatured={fullAgent?.featured ?? false}
          labelIds={fullAgent?.labels?.map((l) => l.id) ?? []}
          onShare={handleShare}
        />
      </shareAgentModal.Provider>

      <agentViewerModal.Provider>
        <AgentViewerModal agent={agentForViewer} />
      </agentViewerModal.Provider>

      <deleteModal.Provider>
        {deleteModal.isOpen && (
          <ConfirmationModalLayout
            icon={SvgTrash}
            title={`Delete "${agent.name}"`}
            onClose={() => deleteModal.toggle(false)}
            submit={
              <Button
                danger
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting…" : "Delete"}
              </Button>
            }
          >
            This agent will be permanently deleted. This action cannot be undone.
          </ConfirmationModalLayout>
        )}
      </deleteModal.Provider>

      <Interactive.Base
        onClick={() => agentViewerModal.toggle(true)}
        group="group/AgentCard"
        variant="none"
      >
        <Card
          padding={0}
          gap={0}
          height="full"
          className="radial-00 hover:shadow-00"
        >
          <div className="flex self-stretch h-[6rem]">
            <CardItemLayout
              icon={(props) => <AgentAvatar agent={agent} {...props} />}
              title={agent.name}
              description={agent.description}
              rightChildren={
                <>
                  {isOwnedByUser && isPaidEnterpriseFeaturesEnabled && !isDynamicAgent && (
                    <IconButton
                      icon={SvgBarChart}
                      tertiary
                      onClick={noProp(() =>
                        router.push(`/ee/agents/stats/${agent.id}` as Route)
                      )}
                      tooltip={t("agentsPage.viewAgentStatsTooltip")}
                      className="hidden group-hover/AgentCard:flex"
                    />
                  )}
                  {canEdit && (
                    <IconButton
                      icon={SvgEdit}
                      tertiary
                      onClick={noProp(() =>
                        router.push(`/app/agents/edit/${routeAgentId}` as Route)
                      )}
                      tooltip={t("agentsPage.editAgentTooltip")}
                      className="hidden group-hover/AgentCard:flex"
                    />
                  )}
                  {canEdit && (
                    <IconButton
                      icon={SvgTrash}
                      tertiary
                      onClick={noProp(() => deleteModal.toggle(true))}
                      tooltip={t("agentsPage.deleteAgentTooltip")}
                      className="hidden group-hover/AgentCard:flex"
                    />
                  )}
                  {isOwnedByUser && !isDynamicAgent && (
                    <IconButton
                      icon={SvgShare}
                      tertiary
                      onClick={noProp(() => shareAgentModal.toggle(true))}
                      tooltip={t("agentsPage.shareAgentTooltip")}
                      className="hidden group-hover/AgentCard:flex"
                    />
                  )}
                  {!isDynamicAgent && (
                    <IconButton
                      icon={pinned ? SvgPinned : SvgPin}
                      tertiary
                      onClick={noProp(() => togglePinnedAgent(agent, !pinned))}
                      tooltip={
                        pinned
                          ? t("agentsPage.unpinFromSidebarTooltip")
                          : t("agentsPage.pinToSidebarTooltip")
                      }
                      className={cn(
                        !pinned && "hidden group-hover/AgentCard:flex"
                      )}
                    />
                  )}
                </>
              }
            />
          </div>

          {/* Footer section - bg-background-tint-01 */}
          <div className="bg-background-tint-01 p-1 flex flex-row items-end justify-between w-full">
            {/* Left side - creator and actions */}
            <div className="flex flex-col gap-1 py-1 px-2">
              <AgentAvailabilityBadge agent={agent} showLabel className="w-fit" />
              <Content
                icon={SvgUser}
                title={ownerEmail}
                sizePreset="secondary"
                variant="body"
                prominence="muted"
              />
              <Content
                icon={SvgActions}
                title={
                  actionCount > 0
                    ? t("agentsPage.actionsCount", { count: actionCount })
                    : t("agentsPage.noActions")
                }
                sizePreset="secondary"
                variant="body"
                prominence="muted"
              />
            </div>

            {/* Right side - Start Chat button */}
            <div className="p-0.5">
              <Button
                tertiary
                rightIcon={SvgBubbleText}
                onClick={noProp(handleStartChat)}
              >
                {t("agentsPage.startChat")}
              </Button>
            </div>
          </div>
        </Card>
      </Interactive.Base>
    </>
  );
}
