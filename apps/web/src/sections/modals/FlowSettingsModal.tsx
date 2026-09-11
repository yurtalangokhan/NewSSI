"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslation } from "react-i18next";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import * as InputLayouts from "@/layouts/input-layouts";
import { Card } from "@/refresh-components/cards";
import AgentIconPicker, {
  type AgentIconValue,
} from "@/refresh-components/agents/AgentIconPicker";
import StarterMessagesField from "@/refresh-components/agents/StarterMessagesField";
import AgentVisibilityFields from "@/refresh-components/agents/AgentVisibilityFields";
import { useUser } from "@/providers/UserProvider";
import {
  useCreateModal,
  useModalClose,
} from "@/refresh-components/contexts/ModalContext";
import ShareAgentModal from "@/sections/modals/ShareAgentModal";
import RefreshButton from "@/refresh-components/buttons/Button";
import { MAX_STARTER_MESSAGES } from "@/lib/constants";
import { createFlow, type FlowMetadataInput } from "@/lib/flows/createFlow";
import { updatePersona } from "@/app/admin/agents/lib";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { SvgLock, SvgUsers, SvgWorkflow } from "@opal/icons";

export interface FlowSettingsModalProps {
  mode: "create" | "edit";
  /** Required in edit mode — the flow persona being renamed/re-configured. */
  agent?: MinimalPersonaSnapshot;
  onSaved?: () => void;
}

function starterMessagesFrom(agent?: MinimalPersonaSnapshot): string[] {
  const values = agent?.starter_messages?.map((s) => s.message) ?? [];
  return Array.from(
    { length: MAX_STARTER_MESSAGES },
    (_, i) => values[i] ?? ""
  );
}

/**
 * Flow metadata — creation and editing share this one modal (spec §5).
 * Creating writes a persona + definition and seeds the draft, then hands
 * the caller the new studio route; editing PATCHes the existing persona
 * in place and reports success without navigating.
 */
export default function FlowSettingsModal({
  mode,
  agent,
  onSaved,
}: FlowSettingsModalProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const { isAdmin, isCurator } = useUser();
  const onClose = useModalClose();
  const optionalTag = ` (${t("common.optional")})`;

  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [icon, setIcon] = useState<AgentIconValue>({
    uploadedImageId: agent?.uploaded_image_id ?? null,
    iconName: agent?.icon_name ?? null,
  });
  const [starterMessages, setStarterMessages] = useState<string[]>(
    starterMessagesFrom(agent)
  );
  const [isPublic, setIsPublic] = useState(agent?.is_public ?? true);
  const [featured, setFeatured] = useState(agent?.featured ?? false);
  // Mirrors the agent editor: the share dialog records who a flow is
  // shared with even before the flow exists, and creation sends it along.
  const [sharedUserIds, setSharedUserIds] = useState<string[]>([]);
  const [sharedGroupIds, setSharedGroupIds] = useState<number[]>([]);
  const [labelIds, setLabelIds] = useState<number[]>([]);
  const shareAgentModal = useCreateModal();
  const isShared =
    isPublic || sharedUserIds.length > 0 || sharedGroupIds.length > 0;
  const [submitting, setSubmitting] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const payload: FlowMetadataInput = {
    name,
    description,
    uploadedImageId: icon.uploadedImageId,
    iconName: icon.iconName,
    starterMessages,
    isPublic,
    featured,
    sharedUserIds,
    sharedGroupIds,
    labelIds,
  };

  async function handleSubmit() {
    setSubmitting(true);
    setNameError(null);
    try {
      if (mode === "create") {
        const { definitionId } = await createFlow(payload);
        router.push(`/app/flows/${definitionId}` as Route);
        return;
      }

      if (!agent) {
        throw new Error("FlowSettingsModal: edit mode requires an agent");
      }

      const response = await updatePersona(agent.id, {
        name: payload.name,
        description: payload.description,
        system_prompt: "",
        replace_base_system_prompt: false,
        task_prompt: "",
        datetime_aware: true,
        document_set_ids: [],
        is_public: payload.isPublic,
        llm_model_provider_override: null,
        llm_model_version_override: null,
        starter_messages: payload.starterMessages
          .filter((message) => message.trim().length > 0)
          .map((message) => ({ name: message, message })),
        users: sharedUserIds,
        groups: sharedGroupIds,
        tool_ids: [],
        search_start_date: null,
        uploaded_image_id: payload.uploadedImageId,
        icon_name: payload.iconName,
        featured: payload.featured,
        label_ids: labelIds,
        user_file_ids: [],
        base_agent: "dynamic-agent",
        graph_schema: "flow",
      });

      if (!response || !response.ok) {
        throw Object.assign(new Error("Flow update failed"), {
          status: response?.status ?? 500,
        });
      }

      onSaved?.();
      onClose?.();
    } catch (error) {
      const status = (error as { status?: number }).status;
      setNameError(
        status === 409
          ? t("flowSettings.nameTakenError")
          : t("flowSettings.createFailedError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <shareAgentModal.Provider>
        <ShareAgentModal
          agentId={agent?.id}
          userIds={sharedUserIds}
          groupIds={sharedGroupIds}
          isPublic={isPublic}
          isFeatured={featured}
          labelIds={labelIds}
          onShare={(
            userIds,
            groupIds,
            nextIsPublic,
            nextIsFeatured,
            nextLabelIds
          ) => {
            setSharedUserIds(userIds);
            setSharedGroupIds(groupIds);
            setIsPublic(nextIsPublic);
            setFeatured(nextIsFeatured);
            setLabelIds(nextLabelIds);
            shareAgentModal.toggle(false);
          }}
        />
      </shareAgentModal.Provider>

      <Modal open onOpenChange={(isOpen) => !isOpen && onClose?.()}>
        <Modal.Content width="md-sm">
          <Modal.Header
            icon={SvgWorkflow}
            title={t(
              mode === "create"
                ? "flowSettings.createTitle"
                : "flowSettings.editTitle"
            )}
            onClose={onClose}
          />
          {/* alignItems="stretch": Modal.Body's own Section defaults to
            items-start, which shrinks every field to its content width —
            that is why these inputs rendered half-width. The agent editor
            avoids it by nesting its fields in a plain stretch column.

            Field furniture otherwise matches AgentEditorPage exactly:
            InputLayouts.Vertical per labelled field, a Card around the
            visibility switches. `name` is deliberately omitted — it only
            mounts Formik's ErrorLayout, and this modal has no Formik. */}
          <Modal.Body alignItems="stretch">
            <div className="flex w-full min-w-0 flex-col gap-4">
              {/* Same grid the editor uses for identity fields: content on
                the left, avatar in an auto-width column on the right. */}
              <div className="grid w-full items-start gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="flex min-w-0 flex-col gap-4">
                  <InputLayouts.Vertical title={t("flowSettings.nameLabel")}>
                    <InputTypeIn
                      data-testid="flow-settings-name"
                      className="w-full"
                      placeholder={t("flowSettings.namePlaceholder")}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                    {nameError && (
                      <span data-testid="flow-settings-name-error">
                        {/* ErrorTextLayout, not InputLayouts.Error: the
                          latter reads the message off Formik, which isn't
                          here. */}
                        <InputLayouts.ErrorTextLayout type="error">
                          {nameError}
                        </InputLayouts.ErrorTextLayout>
                      </span>
                    )}
                  </InputLayouts.Vertical>

                  <InputLayouts.Vertical
                    title={`${t(
                      "flowSettings.descriptionLabel"
                    )}${optionalTag}`}
                  >
                    <InputTextArea
                      data-testid="flow-settings-description"
                      className="w-full"
                      placeholder={t("flowSettings.descriptionPlaceholder")}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                    />
                  </InputLayouts.Vertical>
                </div>

                <div className="flex flex-col sm:w-fit">
                  <InputLayouts.Vertical
                    nonInteractive
                    title={t("flowSettings.avatarLabel")}
                  >
                    <AgentIconPicker
                      name={name}
                      value={icon}
                      onChange={setIcon}
                      variant="flow"
                      size="large"
                    />
                  </InputLayouts.Vertical>
                </div>
              </div>

              <InputLayouts.Vertical
                title={`${t(
                  "flowSettings.starterMessagesLabel"
                )}${optionalTag}`}
                description={t("flowSettings.starterMessagesDescription")}
              >
                <StarterMessagesField
                  value={starterMessages}
                  onChange={setStarterMessages}
                />
              </InputLayouts.Vertical>

              <Card>
                <AgentVisibilityFields
                  isPublic={isPublic}
                  featured={featured}
                  canFeature={isAdmin || isCurator}
                  labelNamespace="flowSettings"
                  // Same affordance as the editor: a button opening the full
                  // share dialog (people, groups, org-wide), not a bare
                  // public switch.
                  footer={
                    <RefreshButton
                      secondary
                      leftIcon={isShared ? SvgUsers : SvgLock}
                      data-testid="flow-settings-share"
                      onClick={() => shareAgentModal.toggle(true)}
                    >
                      {t("agentEditor.shareButton")}
                    </RefreshButton>
                  }
                  onChange={(next) => {
                    setIsPublic(next.isPublic);
                    setFeatured(next.featured);
                  }}
                />
              </Card>
            </div>
          </Modal.Body>
          <Modal.Footer>
            <Button prominence="secondary" onClick={onClose}>
              {t("modals.cancel")}
            </Button>
            <Button
              data-testid="flow-settings-submit"
              disabled={submitting || name.trim().length === 0}
              onClick={handleSubmit}
            >
              {t(
                mode === "create"
                  ? "flowSettings.createSubmit"
                  : "flowSettings.saveSubmit"
              )}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </>
  );
}
