"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import CardSection from "@/components/admin/CardSection";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/admin-routes";
import {
  createMailConfig,
  deleteMailConfig,
  MailConfig,
  MailConfigCreatePayload,
  MailConfigUpdatePayload,
  MailSecurity,
  testMailConfig,
  updateMailConfig,
  useMailConfigs,
} from "@/lib/mailConfigs";
import * as InputLayouts from "@/layouts/input-layouts";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import Pagination from "@/refresh-components/Pagination";
import Separator from "@/refresh-components/Separator";
import Text from "@/refresh-components/texts/Text";
import Modal from "@/refresh-components/Modal";
import { toast } from "@/hooks/useToast";
import {
  SvgCheck,
  SvgCheckCircle,
  SvgEdit,
  SvgPlus,
  SvgServer,
  SvgShare,
  SvgShield,
  SvgTrash,
  SvgAlertTriangle,
  SvgAlertCircle,
  SvgClock,
  SvgSearch,
} from "@opal/icons";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MAIL_CONFIGS]!;
const PAGE_SIZE = 10;

const EMPTY_FORM = {
  id: "",
  name: "",
  host: "",
  port: "587",
  username: "",
  password: "",
  from_email: "",
  from_name: "",
  security: "starttls" as MailSecurity,
  test_to_email: "",
};

type MailConfigFormState = typeof EMPTY_FORM;

function formFromConfig(config: MailConfig): MailConfigFormState {
  return {
    id: config.id,
    name: config.name,
    host: config.host,
    port: String(config.port),
    username: config.username ?? "",
    password: "",
    from_email: config.from_email ?? "",
    from_name: config.from_name ?? "",
    security: config.security,
    test_to_email: config.from_email ?? "",
  };
}

/* ---------- helper for security label ---------- */
function securityLabel(security: MailSecurity) {
  switch (security) {
    case "starttls":
      return "STARTTLS";
    case "ssl":
      return "SSL/TLS";
    case "none":
      return "None";
  }
}

export default function Page() {
  const { t } = useTranslation("common", { keyPrefix: "admin.mailConfigs" });
  const { t: tNav } = useTranslation();

  // Search & Pagination state
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  // Debounce search query changes
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery.trim());
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  const { mailConfigs, totalItems, totalPages, isLoading, refreshMailConfigs } =
    useMailConfigs({
      search: debouncedSearch,
      page: currentPage,
      pageSize: PAGE_SIZE,
    });

  const [form, setForm] = useState<MailConfigFormState>(EMPTY_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [testingConfigId, setTestingConfigId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<MailConfig | null>(null);

  const activeConfigs = useMemo(
    () => mailConfigs.filter((config) => config.is_active),
    [mailConfigs]
  );
  const isEditing = Boolean(form.id);

  /* ---- validation ---- */
  function validateForm(form: MailConfigFormState, isEditing: boolean) {
    if (!form.name.trim()) return t("nameRequired");
    if (!form.host.trim()) return t("hostRequired");
    const port = Number(form.port);
    if (!Number.isInteger(port) || port <= 0 || port > 65535) {
      return t("portRangeError");
    }
    if (!form.username.trim()) return t("usernameRequired");
    if (!isEditing && !form.password.trim()) return t("passwordRequired");
    if (!form.from_email.trim()) return t("fromEmailRequired");
    return null;
  }

  /* ---- payload builders ---- */
  function toCreatePayload(form: MailConfigFormState): MailConfigCreatePayload {
    return {
      name: form.name.trim(),
      host: form.host.trim(),
      port: Number(form.port),
      username: form.username.trim(),
      password: form.password.trim(),
      from_email: form.from_email.trim(),
      from_name: form.from_name.trim() || null,
      security: form.security,
    };
  }

  function toUpdatePayload(form: MailConfigFormState): MailConfigUpdatePayload {
    const payload: MailConfigUpdatePayload = {
      name: form.name.trim(),
      host: form.host.trim(),
      port: Number(form.port),
      username: form.username.trim(),
      from_email: form.from_email.trim(),
      from_name: form.from_name.trim() || null,
      security: form.security,
    };
    if (form.password.trim()) {
      payload.password = form.password.trim();
    }
    return payload;
  }

  /* ---- field setter ---- */
  function setField<K extends keyof MailConfigFormState>(
    field: K,
    value: MailConfigFormState[K]
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  /* ---- open modal helpers ---- */
  function openCreateModal() {
    setForm(EMPTY_FORM);
    setIsModalOpen(true);
  }

  function openEditModal(config: MailConfig) {
    setForm(formFromConfig(config));
    setIsModalOpen(true);
  }

  function closeModal() {
    setIsModalOpen(false);
    setTimeout(() => setForm(EMPTY_FORM), 200);
  }

  /* ---- handlers ---- */
  async function handleSave() {
    const error = validateForm(form, isEditing);
    if (error) {
      toast.error(error);
      return;
    }

    setIsSaving(true);
    try {
      if (isEditing) {
        await updateMailConfig(form.id, toUpdatePayload(form));
        toast.success(t("toastUpdated"));
      } else {
        await createMailConfig(toCreatePayload(form));
        toast.success(t("toastCreated"));
      }
      closeModal();
      await refreshMailConfigs();
    } catch (error) {
      toast.error(t("toastSaveFailed", { error }));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(config: MailConfig) {
    setIsSaving(true);
    try {
      await deleteMailConfig(config.id);
      await refreshMailConfigs();
      toast.success(t("toastDeleted"));
    } catch (error) {
      toast.error(t("toastDeleteFailed", { error }));
    } finally {
      setIsSaving(false);
      setDeleteTarget(null);
    }
  }

  async function handleTest(config: MailConfig) {
    setTestingConfigId(config.id);
    try {
      const result = await testMailConfig(config.id, config.from_email ?? "");
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
      await refreshMailConfigs();
    } catch (error) {
      toast.error(t("toastTestFailed", { error }));
    } finally {
      setTestingConfigId(null);
    }
  }

  const showingFrom = totalItems > 0 ? (currentPage - 1) * PAGE_SIZE + 1 : 0;
  const showingTo = Math.min(currentPage * PAGE_SIZE, totalItems);

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? tNav(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={t("description")}
        rightChildren={
          <Button leftIcon={SvgPlus} onClick={openCreateModal}>
            {t("newButton")}
          </Button>
        }
        separator
      />

      <SettingsLayouts.Body>
        {/* -------- Config List Card -------- */}
        <CardSection className="rounded-08">
          {/* Card Header with Title & Search Bar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
            <div className="flex flex-col gap-1">
              <Text as="p" mainUiBody>
                {t("savedTitle")}
              </Text>
              <Text as="p" secondaryBody text03>
                {isLoading
                  ? t("loadingAccounts")
                  : debouncedSearch
                    ? t("searchResultCount", { count: totalItems })
                    : t("activeConfigCount", { count: totalItems })}
              </Text>
            </div>

            {/* Search Bar */}
            <div className="w-full sm:w-72 md:w-80">
              <InputTypeIn
                leftSearchIcon
                value={searchQuery}
                placeholder={t("searchPlaceholder")}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
          </div>

          <Separator noPadding />

          {/* Loading Skeleton */}
          {isLoading ? (
            <div className="flex flex-col divide-y divide-border-01">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 gap-3 items-center">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-01">
                      <div className="h-5 w-5 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                    </div>
                    <div className="flex min-w-0 flex-col gap-2">
                      <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                      <div className="h-3 w-56 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <div className="h-8 w-16 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                    <div className="h-8 w-16 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                    <div className="h-8 w-16 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                  </div>
                </div>
              ))}
            </div>
          ) : activeConfigs.length === 0 && debouncedSearch ? (
            <div className="flex flex-col items-center gap-3 py-12">
              <div className="flex h-12 w-12 items-center justify-center rounded-12 border border-border-01 bg-background-neutral-01">
                <SvgSearch className="h-6 w-6 stroke-text-04" />
              </div>
              <Text
                as="p"
                secondaryBody
                text03
                className="text-center max-w-sm"
              >
                {t("noSearchResults")}
              </Text>
              <Button secondary onClick={() => setSearchQuery("")}>
                {t("clearSearch")}
              </Button>
            </div>
          ) : activeConfigs.length === 0 ? (
            /* Empty State: No configs exist */
            <div className="flex flex-col items-center gap-3 py-12">
              <div className="flex h-12 w-12 items-center justify-center rounded-12 border border-border-01 bg-background-neutral-01">
                <SvgServer className="h-6 w-6 stroke-text-04" />
              </div>
              <Text
                as="p"
                secondaryBody
                text03
                className="text-center max-w-sm"
              >
                {t("noConfigsYet")}
              </Text>
              <Button secondary leftIcon={SvgPlus} onClick={openCreateModal}>
                {t("newButton")}
              </Button>
            </div>
          ) : (
            /* List of Configs */
            <div className="flex flex-col divide-y divide-border-01">
              {activeConfigs.map((config) => {
                const isTesting = testingConfigId === config.id;
                const isSuccess =
                  config.last_test_status === "success" ||
                  (!config.last_test_status && Boolean(config.last_tested_at));
                const isFailed = config.last_test_status === "failed";
                const isNotTested =
                  !config.last_tested_at && !config.last_test_status;

                return (
                  <div
                    key={config.id}
                    className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    {/* Left: icon + info */}
                    <div className="flex min-w-0 gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-01">
                        <SvgServer className="h-5 w-5 stroke-text-04" />
                      </div>
                      <div className="flex min-w-0 flex-col gap-1">
                        <Text as="p" mainUiBody>
                          {config.name}
                        </Text>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <Text as="span" secondaryBody text03>
                            {config.from_email}
                          </Text>
                          <span className="text-text-03">&middot;</span>
                          <Text as="span" secondaryBody text03>
                            {config.host}:{config.port}
                          </Text>
                          <span className="text-text-03">&middot;</span>
                          <div className="inline-flex items-center gap-1">
                            <SvgShield className="h-3 w-3 stroke-text-04" />
                            <Text as="span" secondaryBody text03>
                              {securityLabel(config.security)}
                            </Text>
                          </div>
                        </div>

                        {/* Status & Last Tested Date */}
                        <div className="flex flex-wrap items-center gap-2">
                          {isSuccess && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-04 text-xs font-medium bg-status-success-00 border border-status-success-02 text-status-success-05">
                              <SvgCheckCircle className="size-3 stroke-status-success-05 shrink-0" />
                              <span>{t("testStatusSuccess")}</span>
                            </span>
                          )}

                          {isFailed && (
                            <span
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-04 text-xs font-medium bg-status-error-00 border border-status-error-02 text-status-error-05"
                              title={config.last_test_error || undefined}
                            >
                              <SvgAlertCircle className="size-3 stroke-status-error-05 shrink-0" />
                              <span>{t("testStatusFailed")}</span>
                            </span>
                          )}

                          {isNotTested && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-04 text-xs font-medium bg-background-neutral-01 border border-border-01 text-text-03">
                              <SvgClock className="size-3 stroke-text-03 shrink-0" />
                              <span>{t("notTestedYet")}</span>
                            </span>
                          )}

                          {config.last_tested_at && (
                            <Text as="span" secondaryBody text03>
                              {t("lastTested", {
                                date: new Date(
                                  config.last_tested_at
                                ).toLocaleString(),
                              })}
                            </Text>
                          )}

                          {isFailed && config.last_test_error && (
                            <span
                              className="text-xs text-status-error-05 max-w-xs md:max-w-md truncate"
                              title={config.last_test_error}
                            >
                              ({config.last_test_error})
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Right: action buttons */}
                    <div className="flex shrink-0 flex-wrap items-center gap-2 sm:ml-3">
                      <Button
                        secondary
                        leftIcon={SvgEdit}
                        onClick={() => openEditModal(config)}
                      >
                        {t("editButton")}
                      </Button>
                      <Button
                        secondary
                        leftIcon={SvgShare}
                        disabled={isTesting}
                        onClick={() => handleTest(config)}
                      >
                        {isTesting ? t("testingButton") : t("testButton")}
                      </Button>
                      <Button
                        danger
                        leftIcon={SvgTrash}
                        disabled={isSaving}
                        onClick={() => setDeleteTarget(config)}
                      >
                        {t("deleteButton")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination Footer */}
          {totalPages > 1 && (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-4 mt-2 border-t border-border-01">
              <Text as="p" secondaryBody text03>
                {t("paginationInfo", {
                  from: showingFrom,
                  to: showingTo,
                  total: totalItems,
                })}
              </Text>
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={setCurrentPage}
              />
            </div>
          )}
        </CardSection>
      </SettingsLayouts.Body>

      {/* -------- Create / Edit Modal -------- */}
      <Modal open={isModalOpen} onOpenChange={(open) => !open && closeModal()}>
        <Modal.Content width="md" preventAccidentalClose>
          <Modal.Header
            icon={isEditing ? SvgEdit : SvgPlus}
            title={isEditing ? t("editConfigTitle") : t("addConfigTitle")}
            description={t("passwordsEncryptedNote")}
            onClose={closeModal}
          />
          <Modal.Body>
            <div className="flex flex-col gap-4 w-full">
              <InputLayouts.Vertical title={t("nameLabel")}>
                <InputTypeIn
                  value={form.name}
                  placeholder={t("namePlaceholder")}
                  onChange={(event) => setField("name", event.target.value)}
                />
              </InputLayouts.Vertical>

              <InputLayouts.Vertical title={t("smtpHostLabel")}>
                <InputTypeIn
                  value={form.host}
                  placeholder={t("smtpHostPlaceholder")}
                  onChange={(event) => setField("host", event.target.value)}
                />
              </InputLayouts.Vertical>

              <div className="grid gap-3 sm:grid-cols-2">
                <InputLayouts.Vertical title={t("portLabel")}>
                  <InputTypeIn
                    value={form.port}
                    inputMode="numeric"
                    placeholder="587"
                    onChange={(event) => setField("port", event.target.value)}
                  />
                </InputLayouts.Vertical>

                <InputLayouts.Vertical title={t("securityLabel")}>
                  <InputSelect
                    value={form.security}
                    onValueChange={(value) =>
                      setField("security", value as MailSecurity)
                    }
                  >
                    <InputSelect.Trigger
                      placeholder={t("securityPlaceholder")}
                    />
                    <InputSelect.Content>
                      <InputSelect.Item value="starttls">
                        STARTTLS
                      </InputSelect.Item>
                      <InputSelect.Item value="ssl">SSL</InputSelect.Item>
                      <InputSelect.Item value="none">None</InputSelect.Item>
                    </InputSelect.Content>
                  </InputSelect>
                </InputLayouts.Vertical>
              </div>

              <Separator noPadding />

              <InputLayouts.Vertical title={t("usernameLabel")}>
                <InputTypeIn
                  value={form.username}
                  placeholder={t("usernamePlaceholder")}
                  onChange={(event) => setField("username", event.target.value)}
                />
              </InputLayouts.Vertical>

              <InputLayouts.Vertical
                title={
                  isEditing ? t("passwordLabelOptional") : t("passwordLabel")
                }
                description={
                  isEditing ? t("passwordLeaveBlankHint") : undefined
                }
              >
                <PasswordInputTypeIn
                  value={form.password}
                  placeholder={
                    isEditing
                      ? t("passwordPlaceholderUnchanged")
                      : t("passwordPlaceholder")
                  }
                  onChange={(event) => setField("password", event.target.value)}
                />
              </InputLayouts.Vertical>

              <Separator noPadding />

              <div className="grid gap-3 sm:grid-cols-2">
                <InputLayouts.Vertical title={t("fromEmailLabel")}>
                  <InputTypeIn
                    value={form.from_email}
                    placeholder="agent@example.com"
                    onChange={(event) =>
                      setField("from_email", event.target.value)
                    }
                  />
                </InputLayouts.Vertical>

                <InputLayouts.Vertical title={t("fromNameLabel")}>
                  <InputTypeIn
                    value={form.from_name}
                    placeholder="Agent Mail"
                    onChange={(event) =>
                      setField("from_name", event.target.value)
                    }
                  />
                </InputLayouts.Vertical>
              </div>

              {isEditing && (
                <InputLayouts.Vertical
                  title={t("testRecipientLabel")}
                  description={t("testRecipientHint")}
                >
                  <InputTypeIn
                    value={form.test_to_email}
                    placeholder={form.from_email || "recipient@example.com"}
                    onChange={(event) =>
                      setField("test_to_email", event.target.value)
                    }
                  />
                </InputLayouts.Vertical>
              )}
            </div>
          </Modal.Body>

          <Modal.Footer>
            <Button secondary onClick={closeModal}>
              {t("cancelButton")}
            </Button>
            <Button
              leftIcon={SvgCheck}
              disabled={isSaving}
              onClick={handleSave}
            >
              {isEditing ? t("saveButton") : t("createButton")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>

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
                {t("cancelButton")}
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
