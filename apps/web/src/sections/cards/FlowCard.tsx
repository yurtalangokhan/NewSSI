"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslation } from "react-i18next";
import type {
  FullPersona,
  MinimalPersonaSnapshot,
} from "@/app/admin/agents/interfaces";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import Chip from "@/refresh-components/Chip";
import Text from "@/refresh-components/texts/Text";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import { Card } from "@/refresh-components/cards";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Interactive } from "@opal/core";
import { Content } from "@opal/layouts";
import { useAppRouter } from "@/hooks/appNavigation";
import { usePinnedAgents, useAgents, useAgent } from "@/hooks/useAgents";
import { useUser } from "@/providers/UserProvider";
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import {
  checkUserOwnsAgent,
  deleteAgent,
  resolveAgentOwnerEmail,
  updateAgentSharedStatus,
  updateAgentFeaturedStatus,
} from "@/lib/agents";
import { isFlowChatReady } from "@/lib/flows/flowAgent";
import { timeAgo } from "@/lib/time";
import { cn, noProp } from "@/lib/utils";
import { toast } from "@/hooks/useToast";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import AgentViewerModal from "@/sections/modals/AgentViewerModal";
import ShareAgentModal from "@/sections/modals/ShareAgentModal";
import {
  SvgBubbleText,
  SvgClock,
  SvgEdit,
  SvgPin,
  SvgPinned,
  SvgShare,
  SvgTrash,
  SvgUser,
} from "@opal/icons";

export interface FlowCardProps {
  agent: MinimalPersonaSnapshot;
}

export default function FlowCard({ agent }: FlowCardProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const route = useAppRouter();
  const { user, isAdmin, isCurator } = useUser();
  const { pinnedAgents, togglePinnedAgent } = usePinnedAgents();
  const { refresh: refreshAgents } = useAgents();
  const isPaidEnterpriseFeaturesEnabled = usePaidEnterpriseFeaturesEnabled();
  const canUpdateFeaturedStatus = isAdmin || isCurator;
  const chatReady = isFlowChatReady(agent);
  const isOwnedByUser = checkUserOwnsAgent(user, agent);
  const canEdit = isOwnedByUser || isAdmin;
  const pinned = useMemo(
    () =>
      pinnedAgents.some(
        (pinnedAgent) => String(pinnedAgent.id) === String(agent.id)
      ),
    [agent.id, pinnedAgents]
  );

  const ownerEmail = useMemo(() => {
    if (agent.owner?.id && user?.id && agent.owner.id === user.id) {
      return user.email;
    }
    return resolveAgentOwnerEmail(agent.owner?.email, t);
  }, [agent.owner?.email, agent.owner?.id, user?.email, user?.id, t]);

  const updatedLabel = useMemo(
    () => timeAgo(agent.flow_updated_at),
    [agent.flow_updated_at]
  );

  // Clicking the card previews the flow (same as an agent card); editing
  // is the explicit pencil action, which opens the full-screen studio.
  const flowViewerModal = useCreateModal();
  const shareAgentModal = useCreateModal();
  const deleteModal = useCreateModal();
  const [isHovered, setIsHovered] = useState(false);
  const shouldLoadAgentDetail =
    flowViewerModal.isOpen || shareAgentModal.isOpen || isHovered;
  const {
    agent: fullAgent,
    isLoading: isAgentLoading,
    refresh: refreshAgent,
  } = useAgent(shouldLoadAgentDetail ? agent.external_id ?? agent.id : null);
  const agentForViewer = useMemo<FullPersona>(() => {
    const base = fullAgent ?? {
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
      rag_config: { document_processing: [], knowledge_graph: [] },
      attached_documents: [],
      search_start_date: null,
    };
    if (base.owner?.id && user?.id && base.owner.id === user.id && user.email) {
      return {
        ...base,
        owner: {
          ...base.owner,
          email: user.email,
        },
      };
    }
    return base;
  }, [fullAgent, agent, user]);

  const openStudio = useCallback(() => {
    if (!agent.agent_definition_id) return;
    router.push(`/app/flows/${agent.agent_definition_id}` as Route);
  }, [agent.agent_definition_id, router]);

  const startChat = useCallback(() => {
    route({ agentId: agent.external_id ?? agent.id });
  }, [route, agent.external_id, agent.id]);

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
        toast.error(t("agentsPage.shareError", { error: shareError }));
        return;
      }
      if (canUpdateFeaturedStatus) {
        const featuredError = await updateAgentFeaturedStatus(
          agent.id,
          isFeatured
        );
        if (featuredError) {
          toast.error(t("agentsPage.featuredError", { error: featuredError }));
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
      t,
    ]
  );

  const [isDeleting, setIsDeleting] = useState(false);
  const handleDelete = useCallback(async () => {
    setIsDeleting(true);
    try {
      const error = await deleteAgent(agent.external_id ?? agent.id);
      if (error) {
        toast.error(t("agentsPage.deleteError", { error }));
      } else {
        toast.success(t("agentsPage.deleteSuccess", { name: agent.name }));
        await refreshAgents();
      }
    } finally {
      setIsDeleting(false);
      deleteModal.toggle(false);
    }
  }, [agent.external_id, agent.id, agent.name, refreshAgents, deleteModal, t]);

  const startChatButton = (
    <Button
      data-testid="flow-card-start-chat"
      tertiary
      disabled={!chatReady}
      rightIcon={SvgBubbleText}
      onClick={noProp(startChat)}
    >
      {t("flowsPage.startChat")}
    </Button>
  );

  return (
    <>
      <flowViewerModal.Provider>
        <AgentViewerModal
          agent={agentForViewer}
          isLoading={shouldLoadAgentDetail && (isAgentLoading || !fullAgent)}
        />
      </flowViewerModal.Provider>

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

      <deleteModal.Provider>
        {deleteModal.isOpen && (
          <ConfirmationModalLayout
            icon={SvgTrash}
            title={t("agentsPage.deleteModalTitle", { name: agent.name })}
            onClose={() => deleteModal.toggle(false)}
            submit={
              <Button danger onClick={handleDelete} disabled={isDeleting}>
                {isDeleting
                  ? t("agentsPage.deleteModalDeleting")
                  : t("agentsPage.deleteModalButton")}
              </Button>
            }
          >
            {t("agentsPage.deleteModalDescription")}
          </ConfirmationModalLayout>
        )}
      </deleteModal.Provider>

      <Interactive.Base
        onClick={() => flowViewerModal.toggle(true)}
        onMouseEnter={() => setIsHovered(true)}
        group="group/FlowCard"
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
                  {canEdit && (
                    <IconButton
                      icon={SvgEdit}
                      tertiary
                      onClick={noProp(openStudio)}
                      tooltip={t("flowsPage.edit")}
                      aria-label={t("flowsPage.edit")}
                      className="hidden group-hover/FlowCard:flex"
                    />
                  )}
                  {canEdit && (
                    <IconButton
                      icon={SvgTrash}
                      tertiary
                      onClick={noProp(() => deleteModal.toggle(true))}
                      tooltip={t("agentsPage.deleteAgentTooltip")}
                      aria-label={t("agentsPage.deleteAgentTooltip")}
                      className="hidden group-hover/FlowCard:flex"
                    />
                  )}
                  {isOwnedByUser && (
                    <IconButton
                      icon={SvgShare}
                      tertiary
                      onClick={noProp(() => shareAgentModal.toggle(true))}
                      tooltip={t("agentsPage.shareAgentTooltip")}
                      aria-label={t("agentsPage.shareAgentTooltip")}
                      className="hidden group-hover/FlowCard:flex"
                    />
                  )}
                  {chatReady && (
                    <IconButton
                      icon={pinned ? SvgPinned : SvgPin}
                      tertiary
                      onClick={noProp(() => togglePinnedAgent(agent, !pinned))}
                      tooltip={
                        pinned
                          ? t("agentsPage.unpinFromSidebarTooltip")
                          : t("agentsPage.pinToSidebarTooltip")
                      }
                      aria-label={
                        pinned
                          ? t("agentsPage.unpinFromSidebarTooltip")
                          : t("agentsPage.pinToSidebarTooltip")
                      }
                      className={cn(
                        !pinned && "hidden group-hover/FlowCard:flex"
                      )}
                    />
                  )}
                </>
              }
            />
          </div>

          {/* Footer mirrors AgentCard: metadata on the left, the single
              primary action on the right. */}
          <div className="bg-background-tint-01 p-1 flex flex-row items-end justify-between w-full">
            <div className="flex flex-col gap-1 py-1 px-2 min-w-0">
              <div className="flex flex-row items-center gap-1.5">
                <span data-testid="flow-card-version">
                  <Chip>{versionLabelFor(agent, t)}</Chip>
                </span>
                {agent.flow_has_draft && (
                  <span data-testid="flow-card-draft-badge">
                    <Chip>{t("flowsPage.draftAhead")}</Chip>
                  </span>
                )}
              </div>
              <Content
                icon={SvgUser}
                title={ownerEmail}
                sizePreset="secondary"
                variant="body"
                prominence="muted"
              />
              {updatedLabel && (
                <Content
                  icon={SvgClock}
                  title={t("flowsPage.updatedAt", { date: updatedLabel })}
                  sizePreset="secondary"
                  variant="body"
                  prominence="muted"
                />
              )}
            </div>

            <div className="p-0.5 shrink-0">
              {chatReady ? (
                startChatButton
              ) : (
                <SimpleTooltip tooltip={t("flowsPage.notPublishedTooltip")}>
                  {/* a disabled button emits no pointer events; the span carries them */}
                  <span>{startChatButton}</span>
                </SimpleTooltip>
              )}
            </div>
          </div>
        </Card>
      </Interactive.Base>
    </>
  );
}

function versionLabelFor(
  agent: MinimalPersonaSnapshot,
  t: (key: string, options?: Record<string, unknown>) => string
): string {
  return agent.flow_published_version_no
    ? t("flowsPage.versionChip", { version: agent.flow_published_version_no })
    : t("flowsPage.notPublished");
}
