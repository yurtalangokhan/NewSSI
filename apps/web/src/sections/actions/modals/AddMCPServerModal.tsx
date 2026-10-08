"use client";

import { useMemo, useState } from "react";
import { Formik, Form } from "formik";
import Modal from "@/refresh-components/Modal";
import * as InputLayouts from "@/layouts/input-layouts";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import Button from "@/refresh-components/buttons/Button";
import { createMCPServer, updateMCPServer } from "@/lib/api/domains/tools/api";
import {
  MCPServerCreateRequest,
  MCPServerStatus,
  MCPServer,
} from "@/lib/tools/interfaces";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import Separator from "@/refresh-components/Separator";
import { Button as OpalButton } from "@opal/components";
import { toast } from "@/hooks/useToast";
import { ModalCreationInterface } from "@/refresh-components/contexts/ModalContext";
import { SvgCheckCircle, SvgServer, SvgUnplug } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";
import { useUser } from "@/providers/UserProvider";
import { buildMCPServerValidationSchema } from "./mcpServerValidation";

interface AddMCPServerModalProps {
  skipOverlay?: boolean;
  activeServer: MCPServer | null;
  setActiveServer: (server: MCPServer | null) => void;
  disconnectModal: ModalCreationInterface;
  manageServerModal: ModalCreationInterface;
  onServerCreated?: (server: MCPServer) => void;
  handleAuthenticate: (serverId: number) => void;
  mutateMcpServers?: () => Promise<void>;
}

export default function AddMCPServerModal({
  skipOverlay = false,
  activeServer,
  disconnectModal,
  manageServerModal,
  onServerCreated,
  handleAuthenticate,
  mutateMcpServers,
}: AddMCPServerModalProps) {
  const { t } = useTranslation();
  const { isOpen, toggle } = useModal();
  const { hasPermission } = useUser();
  // Only a system admin may change a provider's definition (name/url): those
  // live on the MCP Configuration page. Enterprise admins authenticate the
  // provider here but must not rename or re-point it.
  const canEditDefinition = hasPermission("mcp_provider:update");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const validationSchema = useMemo(
    () => buildMCPServerValidationSchema(t),
    [t]
  );

  // Use activeServer from props
  const server = activeServer;

  // Handler for disconnect button
  const handleDisconnectClick = () => {
    if (activeServer) {
      // Server stays the same, just toggle modals
      manageServerModal.toggle(false);
      disconnectModal.toggle(true);
    }
  };

  // Determine if we're in edit mode
  const isEditMode = !!server;

  const initialValues: MCPServerCreateRequest = {
    name: server?.name || "",
    description: server?.description || "",
    server_url: server?.server_url || "",
  };

  const handleSubmit = async (values: MCPServerCreateRequest) => {
    setIsSubmitting(true);

    try {
      if (isEditMode && server) {
        // Update existing server
        await updateMCPServer(server.id, values);
        toast.success(t("admin.mcp.serverUpdated"));
        await mutateMcpServers?.();
      } else {
        // Create new server
        const createdServer = await createMCPServer(values);

        toast.success(t("admin.mcp.serverCreated"));

        await mutateMcpServers?.();

        if (onServerCreated) {
          onServerCreated(createdServer);
        }
      }
      // Close modal. Do NOT clear `activeServer` here because this modal
      // frequently transitions to other modals (authenticate/disconnect), and
      // clearing would race those flows.
      toggle(false);
    } catch (error) {
      console.error(
        `Error ${isEditMode ? "updating" : "creating"} MCP server:`,
        error
      );
      toast.error(
        error instanceof Error
          ? error.message
          : t(isEditMode ? "admin.mcp.updateFailed" : "admin.mcp.createFailed")
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle modal close to clear server state
  const handleModalClose = (open: boolean) => {
    toggle(open);
  };

  return (
    <Modal open={isOpen} onOpenChange={handleModalClose}>
      <Modal.Content
        width="sm"
        height="lg"
        preventAccidentalClose={false}
        skipOverlay={skipOverlay}
      >
        <Formik
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
        >
          {({ isValid, dirty }) => (
            <Form>
              <Modal.Header
                icon={SvgServer}
                title={
                  isEditMode
                    ? t("admin.mcp.manageServer")
                    : t("admin.mcp.addServer")
                }
                description={
                  isEditMode
                    ? t("admin.mcp.manageServerDescription")
                    : t("admin.mcp.addServerDescription")
                }
                onClose={() => handleModalClose(false)}
              />

              <Modal.Body>
                {!canEditDefinition && (
                  <Text as="p" secondaryBody text03>
                    {t("admin.mcp.definitionReadOnly", {
                      defaultValue:
                        "Server details are managed by a system admin on the MCP Configuration page. You can add or update credentials here.",
                    })}
                  </Text>
                )}

                <InputLayouts.Vertical
                  name="name"
                  title={t("admin.mcp.serverName")}
                >
                  <InputTypeInField
                    name="name"
                    placeholder={t("admin.mcp.serverNamePlaceholder")}
                    variant={canEditDefinition ? "primary" : "disabled"}
                    autoFocus
                  />
                </InputLayouts.Vertical>

                <InputLayouts.Vertical
                  name="description"
                  title={`${t("admin.mcp.description")} (${t(
                    "admin.mcp.optional"
                  )})`}
                >
                  <InputTextAreaField
                    name="description"
                    placeholder={t("admin.mcp.serverDescriptionPlaceholder")}
                    variant={canEditDefinition ? "primary" : "disabled"}
                    rows={3}
                  />
                </InputLayouts.Vertical>

                <Separator noPadding />

                <InputLayouts.Vertical
                  name="server_url"
                  title={t("admin.mcp.serverUrl")}
                  subDescription={t("admin.mcp.serverUrlHint")}
                >
                  <InputTypeInField
                    name="server_url"
                    placeholder={t("admin.mcp.serverUrlPlaceholder")}
                    variant={canEditDefinition ? "primary" : "disabled"}
                  />
                </InputLayouts.Vertical>

                {/* Authentication Status Section - Only show in edit mode when authenticated */}
                {isEditMode &&
                  server?.is_authenticated &&
                  server?.status === MCPServerStatus.CONNECTED && (
                    <Section
                      flexDirection="row"
                      justifyContent="between"
                      alignItems="start"
                      gap={1}
                    >
                      <Section gap={0.25} alignItems="start">
                        <Section
                          flexDirection="row"
                          gap={0.5}
                          alignItems="center"
                          width="fit"
                        >
                          <SvgCheckCircle className="w-4 h-4 stroke-status-success-05" />
                          <Text>{t("admin.mcp.authenticatedConnected")}</Text>
                        </Section>
                        <Text secondaryBody text03>
                          {server.auth_type === "OAUTH"
                            ? t("admin.mcp.oauthConnectedTo", {
                                owner: server.owner,
                              })
                            : server.auth_type === "API_TOKEN"
                              ? t("admin.mcp.apiTokenConfigured")
                              : t("admin.mcp.connected")}
                        </Text>
                      </Section>
                      <Section
                        flexDirection="row"
                        gap={0.5}
                        alignItems="center"
                        width="fit"
                      >
                        <OpalButton
                          icon={SvgUnplug}
                          prominence="tertiary"
                          type="button"
                          tooltip={t("admin.mcp.disconnectServer")}
                          onClick={handleDisconnectClick}
                        />
                        <Button
                          secondary
                          type="button"
                          onClick={() => {
                            // Close this modal and open the auth modal for this server
                            toggle(false);
                            handleAuthenticate(server.id);
                          }}
                        >
                          {t("admin.mcp.editConfigs")}
                        </Button>
                      </Section>
                    </Section>
                  )}
              </Modal.Body>

              <Modal.Footer>
                <Button
                  secondary
                  type="button"
                  onClick={() => handleModalClose(false)}
                  disabled={isSubmitting}
                >
                  {t("modals.cancel")}
                </Button>
                <Button
                  primary
                  type="submit"
                  disabled={
                    isSubmitting || !isValid || !dirty || !canEditDefinition
                  }
                >
                  {isSubmitting
                    ? isEditMode
                      ? t("admin.mcp.saving")
                      : t("admin.mcp.adding")
                    : isEditMode
                      ? t("admin.mcp.saveChanges")
                      : t("admin.mcp.addServer")}
                </Button>
              </Modal.Footer>
            </Form>
          )}
        </Formik>
      </Modal.Content>
    </Modal>
  );
}
