"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import CardSection from "@/components/admin/CardSection";
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
import Separator from "@/refresh-components/Separator";
import Text from "@/refresh-components/texts/Text";
import { toast } from "@/hooks/useToast";
import { SvgCheck, SvgEdit, SvgPlus, SvgShare, SvgTrash } from "@opal/icons";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MAIL_CONFIGS]!;

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
    username: config.username,
    password: "",
    from_email: config.from_email,
    from_name: config.from_name ?? "",
    security: config.security,
    test_to_email: config.from_email,
  };
}

export default function Page() {
  const { t } = useTranslation("common", { keyPrefix: "admin.mailConfigs" });
  const { t: tNav } = useTranslation();
  const { mailConfigs, isLoading, refreshMailConfigs } = useMailConfigs();
  const [form, setForm] = useState<MailConfigFormState>(EMPTY_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [testingConfigId, setTestingConfigId] = useState<string | null>(null);
  const activeConfigs = useMemo(
    () => mailConfigs.filter((config) => config.is_active),
    [mailConfigs]
  );
  const isEditing = Boolean(form.id);

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

  function setField<K extends keyof MailConfigFormState>(
    field: K,
    value: MailConfigFormState[K]
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

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
      setForm(EMPTY_FORM);
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
      if (form.id === config.id) {
        setForm(EMPTY_FORM);
      }
      await refreshMailConfigs();
      toast.success(t("toastDeleted"));
    } catch (error) {
      toast.error(t("toastDeleteFailed", { error }));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTest(config: MailConfig) {
    const toEmail =
      form.id === config.id && form.test_to_email.trim()
        ? form.test_to_email.trim()
        : config.from_email;
    setTestingConfigId(config.id);
    try {
      const result = await testMailConfig(config.id, toEmail);
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
        separator
      />
      <SettingsLayouts.Body>
        <div className="grid w-full gap-6 pb-36 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <CardSection className="rounded-08">
            <div className="flex flex-col gap-4">
              <div className="flex flex-row items-center justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <Text as="p" mainUiBody>
                    {t("savedTitle")}
                  </Text>
                  <Text as="p" secondaryBody text03>
                    {isLoading
                      ? t("loadingAccounts")
                      : t("activeConfigCount", { count: activeConfigs.length })}
                  </Text>
                </div>
                <Button leftIcon={SvgPlus} onClick={() => setForm(EMPTY_FORM)}>
                  {t("newButton")}
                </Button>
              </div>

              <Separator noPadding />

              {activeConfigs.length === 0 && !isLoading ? (
                <div className="flex flex-col gap-2 py-8 text-center">
                  <Text as="p" mainContentMuted text03>
                    {t("noConfigsYet")}
                  </Text>
                </div>
              ) : (
                <div className="flex flex-col divide-y divide-border-01">
                  {activeConfigs.map((config) => (
                    <div
                      key={config.id}
                      className="grid gap-3 py-4 lg:grid-cols-[minmax(0,1fr)_auto]"
                    >
                      <div className="min-w-0">
                        <Text as="p" mainUiBody>
                          {config.name}
                        </Text>
                        <Text as="p" secondaryBody text03>
                          {config.from_email} - {config.host}:{config.port} -{" "}
                          {config.security.toUpperCase()}
                        </Text>
                        <Text as="p" secondaryBody text03>
                          {config.last_tested_at
                            ? t("lastTested", {
                                date: new Date(
                                  config.last_tested_at
                                ).toLocaleString(),
                              })
                            : t("notTestedYet")}
                        </Text>
                      </div>
                      <div className="flex flex-row flex-wrap justify-end gap-2">
                        <Button
                          secondary
                          leftIcon={SvgEdit}
                          onClick={() => setForm(formFromConfig(config))}
                        >
                          {t("editButton")}
                        </Button>
                        <Button
                          secondary
                          leftIcon={SvgShare}
                          disabled={testingConfigId === config.id}
                          onClick={() => handleTest(config)}
                        >
                          {t("testButton")}
                        </Button>
                        <Button
                          danger
                          leftIcon={SvgTrash}
                          disabled={isSaving}
                          onClick={() => handleDelete(config)}
                        >
                          {t("deleteButton")}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardSection>

          <CardSection className="rounded-08">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  {isEditing ? t("editConfigTitle") : t("addConfigTitle")}
                </Text>
                <Text as="p" secondaryBody text03>
                  {t("passwordsEncryptedNote")}
                </Text>
              </div>

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

              <div className="flex flex-row justify-end gap-2">
                {isEditing && (
                  <Button secondary onClick={() => setForm(EMPTY_FORM)}>
                    {t("cancelButton")}
                  </Button>
                )}
                <Button
                  leftIcon={SvgCheck}
                  disabled={isSaving}
                  onClick={handleSave}
                >
                  {isEditing ? t("saveButton") : t("createButton")}
                </Button>
              </div>
            </div>
          </CardSection>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
