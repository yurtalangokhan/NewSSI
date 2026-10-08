"use client";

import { useMemo, useState } from "react";
import { Formik, Form } from "formik";
import * as Yup from "yup";
import { useTranslation } from "react-i18next";

import CardSection from "@/components/admin/CardSection";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/navigation/admin-routes";
import {
  createMCPServer,
  deleteMCPServer,
  updateMCPServer,
  validateMCPServer,
} from "@/lib/api/domains/tools/api";
import type { MCPServerValidationResult } from "@/lib/api/domains/tools/api";
import { useMcpServers } from "@/lib/api/domains/tools/hooks";
import type { MCPServer, MCPServerCreateRequest } from "@/lib/tools/interfaces";
import { isBuiltinMcpServer } from "@/lib/tools/mcpUtils";
import * as InputLayouts from "@/layouts/input-layouts";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Button from "@/refresh-components/buttons/Button";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Modal from "@/refresh-components/Modal";
import McpProviderListSkeleton from "@/refresh-components/skeletons/McpProviderListSkeleton";
import Separator from "@/refresh-components/Separator";
import Text from "@/refresh-components/texts/Text";
import { toast } from "@/hooks/useToast";
import {
  SvgAlertTriangle,
  SvgCheckCircle,
  SvgEdit,
  SvgMcp,
  SvgPlus,
  SvgTrash,
} from "@opal/icons";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MCP_CONFIG]!;

const EMPTY_FORM: MCPServerCreateRequest = {
  name: "",
  description: "",
  server_url: "",
};

/**
 * Provider registration page. Only reachable by system admins because the
 * route config requires `mcp_provider:configure`; enterprise admins authenticate
 * these providers from `/admin/actions/mcp` instead of registering them.
 */
export default function McpConfigurationPage() {
  const { t } = useTranslation("common", { keyPrefix: "admin.mcpConfig" });
  const { t: tNav } = useTranslation();
  const { mcpData, isLoading, mutateMcpServers } = useMcpServers();

  const [searchQuery, setSearchQuery] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<MCPServer | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MCPServer | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Result of the "Verify" probe, keyed by the URL it was run against so a
  // subsequent edit invalidates it (Save stays disabled until re-verified).
  const [probe, setProbe] = useState<{
    url: string;
    result: MCPServerValidationResult;
  } | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);

  const validationSchema = useMemo(
    () =>
      Yup.object().shape({
        name: Yup.string().required(t("nameRequired")),
        description: Yup.string(),
        server_url: Yup.string()
          .url(t("urlInvalid"))
          .required(t("urlRequired")),
      }),
    [t]
  );

  const providers = useMemo(() => {
    const servers = (mcpData?.mcp_servers ?? []) as MCPServer[];
    const external = servers.filter((server) => !isBuiltinMcpServer(server));
    const query = searchQuery.trim().toLowerCase();
    if (!query) return external;
    return external.filter((server) =>
      [server.name, server.server_url, server.description ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [mcpData?.mcp_servers, searchQuery]);

  const openCreate = () => {
    setEditing(null);
    setProbe(null);
    setFormOpen(true);
  };

  const openEdit = (server: MCPServer) => {
    setEditing(server);
    setProbe(null);
    setFormOpen(true);
  };

  const handleVerify = async (url: string) => {
    setIsVerifying(true);
    try {
      const result = await validateMCPServer({ server_url: url });
      setProbe({ url, result });
      if (!result.valid) {
        toast.error(t("verifyInvalidToast"));
      }
    } catch (error) {
      setProbe(null);
      toast.error(
        error instanceof Error ? error.message : t("verifyFailedToast")
      );
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSave = async (values: MCPServerCreateRequest) => {
    setIsSaving(true);
    try {
      if (editing) {
        await updateMCPServer(editing.id, values);
        toast.success(t("updatedToast"));
      } else {
        await createMCPServer(values);
        toast.success(t("createdToast"));
      }
      await mutateMcpServers();
      setFormOpen(false);
      setEditing(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("saveFailedToast")
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (server: MCPServer) => {
    setIsSaving(true);
    try {
      await deleteMCPServer(server.id);
      toast.success(t("deletedToast"));
      await mutateMcpServers();
      setDeleteTarget(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("deleteFailedToast")
      );
    } finally {
      setIsSaving(false);
    }
  };

  const initialValues: MCPServerCreateRequest = editing
    ? {
        name: editing.name,
        description: editing.description ?? "",
        server_url: editing.server_url,
      }
    : EMPTY_FORM;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={tNav(route.titleKey || "", { defaultValue: route.title })}
        description={tNav(route.descriptionKey || "", {
          defaultValue: route.description,
        })}
        separator
      />

      <SettingsLayouts.Body>
        <CardSection className="rounded-08">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
            <div className="flex flex-col gap-1">
              <Text as="p" mainUiBody>
                {t("savedTitle")}
              </Text>
              <Text as="p" secondaryBody text03>
                {isLoading
                  ? t("loadingProviders")
                  : t("providerCount", { count: providers.length })}
              </Text>
            </div>

            <div className="flex items-center gap-3">
              <div className="w-full sm:w-64">
                <InputTypeIn
                  leftSearchIcon
                  variant={isLoading ? "disabled" : "primary"}
                  value={searchQuery}
                  placeholder={t("searchPlaceholder")}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
              </div>
              <Button primary leftIcon={SvgPlus} onClick={openCreate}>
                {t("addButton")}
              </Button>
            </div>
          </div>

          <Separator noPadding />

          {isLoading ? (
            <McpProviderListSkeleton />
          ) : providers.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <div className="flex h-12 w-12 items-center justify-center rounded-12 border border-border-01 bg-background-neutral-01">
                <SvgMcp className="h-6 w-6 stroke-text-04" size={24} />
              </div>
              <Text
                as="p"
                secondaryBody
                text03
                className="text-center max-w-sm"
              >
                {searchQuery ? t("noSearchResults") : t("noProvidersYet")}
              </Text>
            </div>
          ) : (
            <div className="flex flex-col divide-y divide-border-01">
              {providers.map((server) => (
                <div
                  key={server.id}
                  className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-01">
                      <SvgMcp className="h-5 w-5 stroke-text-04" size={20} />
                    </div>
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <Text as="p" mainUiBody>
                        {server.name}
                      </Text>
                      {server.description ? (
                        <Text as="p" secondaryBody text03 className="truncate">
                          {server.description}
                        </Text>
                      ) : null}
                      <Text
                        as="p"
                        secondaryBody
                        text03
                        className="truncate opacity-70"
                      >
                        {server.server_url}
                      </Text>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      secondary
                      leftIcon={SvgEdit}
                      onClick={() => openEdit(server)}
                    >
                      {t("editButton")}
                    </Button>
                    <Button
                      danger
                      leftIcon={SvgTrash}
                      onClick={() => setDeleteTarget(server)}
                    >
                      {t("deleteButton")}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardSection>
      </SettingsLayouts.Body>

      {/* -------- Create / Edit Modal -------- */}
      {formOpen && (
        <Modal open onOpenChange={(open) => !open && setFormOpen(false)}>
          <Modal.Content width="sm">
            <Formik
              initialValues={initialValues}
              enableReinitialize
              validationSchema={validationSchema}
              onSubmit={handleSave}
            >
              {({ isValid, dirty, isSubmitting, values }) => {
                // Save is allowed once the URL is verified as MCP, or when an
                // edit leaves the already-registered URL untouched.
                const urlUnchanged =
                  !!editing && values.server_url === editing.server_url;
                const verified =
                  probe?.url === values.server_url && probe.result.valid;
                const canSave = verified || urlUnchanged;
                const showInvalid =
                  probe?.url === values.server_url && !probe.result.valid;

                return (
                  <Form>
                    <Modal.Header
                      icon={SvgMcp}
                      title={editing ? t("editTitle") : t("addTitle")}
                      description={
                        editing ? t("editDescription") : t("addDescription")
                      }
                      onClose={() => setFormOpen(false)}
                    />
                    <Modal.Body>
                      <InputLayouts.Vertical name="name" title={t("nameLabel")}>
                        <InputTypeInField
                          name="name"
                          placeholder={t("namePlaceholder")}
                          autoFocus
                        />
                      </InputLayouts.Vertical>

                      <InputLayouts.Vertical
                        name="description"
                        title={t("descriptionLabel")}
                      >
                        <InputTextAreaField
                          name="description"
                          placeholder={t("descriptionPlaceholder")}
                          rows={3}
                        />
                      </InputLayouts.Vertical>

                      <Separator noPadding />

                      <InputLayouts.Vertical
                        name="server_url"
                        title={t("urlLabel")}
                        description={t("urlHint")}
                      >
                        <InputTypeInField
                          name="server_url"
                          placeholder={t("urlPlaceholder")}
                        />
                      </InputLayouts.Vertical>

                      {verified && probe ? (
                        <div className="flex items-center gap-2">
                          <SvgCheckCircle className="h-4 w-4 stroke-status-success-05" />
                          <Text as="p" secondaryBody text03>
                            {probe.result.auth_required
                              ? t("verifyAuthRequired")
                              : t("verifyValid", {
                                  count: probe.result.tool_count,
                                })}
                          </Text>
                        </div>
                      ) : null}

                      {showInvalid ? (
                        <div className="flex items-center gap-2">
                          <SvgAlertTriangle className="h-4 w-4 stroke-status-error-05" />
                          <Text as="p" secondaryBody text03>
                            {t("verifyInvalid")}
                          </Text>
                        </div>
                      ) : null}
                    </Modal.Body>
                    <Modal.Footer>
                      <Button secondary onClick={() => setFormOpen(false)}>
                        {tNav("modals.cancel")}
                      </Button>
                      <Button
                        secondary
                        type="button"
                        disabled={!values.server_url || isVerifying}
                        onClick={() => handleVerify(values.server_url)}
                      >
                        {isVerifying ? t("verifyingButton") : t("verifyButton")}
                      </Button>
                      <Button
                        primary
                        type="submit"
                        disabled={
                          isSaving ||
                          isSubmitting ||
                          !isValid ||
                          !dirty ||
                          !canSave
                        }
                      >
                        {editing ? t("saveButton") : t("createButton")}
                      </Button>
                    </Modal.Footer>
                  </Form>
                );
              }}
            </Formik>
          </Modal.Content>
        </Modal>
      )}

      {/* -------- Delete Confirmation Modal -------- */}
      {deleteTarget && (
        <Modal open onOpenChange={(open) => !open && setDeleteTarget(null)}>
          <Modal.Content width="sm">
            <Modal.Header
              icon={SvgAlertTriangle}
              title={t("deleteConfirmTitle")}
              description={t("deleteConfirmDescription", {
                name: deleteTarget.name,
              })}
              onClose={() => setDeleteTarget(null)}
            />
            <Modal.Footer>
              <Button secondary onClick={() => setDeleteTarget(null)}>
                {tNav("modals.cancel")}
              </Button>
              <Button
                danger
                leftIcon={SvgTrash}
                disabled={isSaving}
                onClick={() => handleDelete(deleteTarget)}
              >
                {t("deleteButton")}
              </Button>
            </Modal.Footer>
          </Modal.Content>
        </Modal>
      )}
    </SettingsLayouts.Root>
  );
}
