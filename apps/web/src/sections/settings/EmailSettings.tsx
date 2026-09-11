"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Content } from "@opal/layouts";
import { SvgCheck, SvgShare, SvgTrash } from "@opal/icons";

import * as InputLayouts from "@/layouts/input-layouts";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { Section } from "@/layouts/general-layouts";
import {
  deleteUserMailSettings,
  saveUserMailSettings,
  testUserMailSettings,
  useAvailableMailConfigs,
  useUserMailSettings,
} from "@/lib/mailConfigs";
import Button from "@/refresh-components/buttons/Button";
import Card from "@/refresh-components/cards/Card";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import { toast } from "@/hooks/useToast";
import { EmailSettingsSkeleton } from "@/refresh-components/skeletons/SettingsSkeletons";

export function EmailSettings({
  isLoading: isLoadingProp,
}: { isLoading?: boolean } = {}) {
  const { t } = useTranslation();
  const {
    userMailSettings,
    isLoading: areUserSettingsLoading,
    refreshUserMailSettings,
  } = useUserMailSettings();
  const { availableMailConfigs, isLoading: areMailConfigsLoading } =
    useAvailableMailConfigs();
  const [mailConfigId, setMailConfigId] = useState("");
  const [emailUsername, setEmailUsername] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [fromName, setFromName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  useEffect(() => {
    if (!userMailSettings) return;
    setMailConfigId(userMailSettings.mail_config_id);
    setEmailUsername(userMailSettings.username || "");
    setEmailPassword("");
    setFromEmail(userMailSettings.from_email || "");
    setFromName(userMailSettings.from_name || "");
  }, [userMailSettings]);

  useEffect(() => {
    if (!userMailSettings && availableMailConfigs.length === 1) {
      setMailConfigId(availableMailConfigs[0]!.id);
    }
  }, [availableMailConfigs, userMailSettings]);

  async function saveSettings() {
    if (areUserSettingsLoading) return;
    if (!mailConfigId) {
      toast.error(t("settings.accounts.mailConfigRequired"));
      return;
    }
    if (!emailUsername.trim()) {
      toast.error(`${t("settings.accounts.emailUsernameLabel")} required`);
      return;
    }
    if (!userMailSettings?.password_configured && !emailPassword.trim()) {
      toast.error(`${t("settings.accounts.emailPasswordLabel")} required`);
      return;
    }
    if (!fromEmail.trim()) {
      toast.error(`${t("settings.accounts.fromEmailLabel")} required`);
      return;
    }

    setIsSaving(true);
    try {
      await saveUserMailSettings({
        mail_config_id: mailConfigId,
        username: emailUsername.trim(),
        password: emailPassword.trim() || undefined,
        from_email: fromEmail.trim(),
        from_name: fromName.trim() || null,
      });
      setEmailPassword("");
      await refreshUserMailSettings();
      toast.success(t("settings.accounts.toastEmailConfigSaved"));
    } catch (error) {
      toast.error(t("settings.accounts.toastEmailConfigSaveFailed", { error }));
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteSettings() {
    setShowDeleteModal(false);
    setIsSaving(true);
    try {
      await deleteUserMailSettings();
      setEmailUsername("");
      setEmailPassword("");
      setFromEmail("");
      setFromName("");
      setMailConfigId(
        availableMailConfigs.length === 1 ? availableMailConfigs[0]!.id : ""
      );
      await refreshUserMailSettings();
      toast.success(t("settings.accounts.toastEmailConfigDeleted"));
    } catch (error) {
      toast.error(
        t("settings.accounts.toastEmailConfigDeleteFailed", { error })
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function testSettings() {
    if (areUserSettingsLoading) return;
    if (!mailConfigId) {
      toast.error(t("settings.accounts.mailConfigRequired"));
      return;
    }
    setIsTesting(true);
    try {
      const result = await testUserMailSettings(
        mailConfigId,
        fromEmail.trim() || undefined
      );
      if (result.success) {
        toast.success(
          result.message || t("settings.accounts.toastEmailTestSuccess")
        );
      } else {
        toast.error(
          result.message ||
            t("settings.accounts.toastEmailTestFailed", {
              error: "Unknown error",
            })
        );
      }
      await refreshUserMailSettings();
    } catch (error) {
      toast.error(t("settings.accounts.toastEmailTestFailed", { error }));
    } finally {
      setIsTesting(false);
    }
  }

  if (
    isLoadingProp ||
    (areMailConfigsLoading &&
      (!availableMailConfigs || availableMailConfigs.length === 0))
  ) {
    return <EmailSettingsSkeleton />;
  }

  return (
    <Section gap={0.75}>
      <Content
        title={t("settings.accounts.emailConfigTitle")}
        description={t("settings.accounts.emailConfigDescription")}
        sizePreset="main-content"
        variant="section"
        widthVariant="full"
      />
      <Card>
        {areUserSettingsLoading && (
          <div
            aria-label="grid-loading"
            className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse my-2"
          />
        )}
        <InputLayouts.Horizontal
          title={t("settings.accounts.mailConfigLabel")}
          description={t("settings.accounts.mailConfigDescription")}
          center
        >
          <InputSelect
            value={mailConfigId}
            onValueChange={setMailConfigId}
            disabled={
              areMailConfigsLoading || availableMailConfigs.length === 0
            }
          >
            <InputSelect.Trigger
              placeholder={
                areMailConfigsLoading
                  ? t("settings.accounts.mailConfigLoading")
                  : t("settings.accounts.mailConfigPlaceholder")
              }
            />
            <InputSelect.Content>
              {availableMailConfigs.map((config) => (
                <InputSelect.Item key={config.id} value={config.id}>
                  {config.name} ({config.host}:{config.port})
                </InputSelect.Item>
              ))}
            </InputSelect.Content>
          </InputSelect>
        </InputLayouts.Horizontal>

        <InputLayouts.Horizontal
          title={t("settings.accounts.emailUsernameLabel")}
          description={t("settings.accounts.emailUsernameDescription")}
          center
        >
          <InputTypeIn
            placeholder={t("settings.accounts.emailUsernamePlaceholder")}
            value={emailUsername}
            onChange={(event) => setEmailUsername(event.target.value)}
          />
        </InputLayouts.Horizontal>

        <InputLayouts.Horizontal
          title={t("settings.accounts.emailPasswordLabel")}
          description={
            userMailSettings?.password_configured
              ? t("settings.accounts.emailPasswordConfiguredHint")
              : t("settings.accounts.emailPasswordDescription")
          }
          center
        >
          <PasswordInputTypeIn
            placeholder={
              userMailSettings?.password_configured
                ? t("settings.accounts.emailPasswordPlaceholderConfigured")
                : t("settings.accounts.emailPasswordPlaceholder")
            }
            value={emailPassword}
            onChange={(event) => setEmailPassword(event.target.value)}
          />
        </InputLayouts.Horizontal>

        <InputLayouts.Horizontal
          title={t("settings.accounts.fromEmailLabel")}
          description={t("settings.accounts.fromEmailDescription")}
          center
        >
          <InputTypeIn
            placeholder="user@example.com"
            value={fromEmail}
            onChange={(event) => setFromEmail(event.target.value)}
          />
        </InputLayouts.Horizontal>

        <InputLayouts.Horizontal
          title={t("settings.accounts.fromNameLabel")}
          description={t("settings.accounts.fromNameDescription")}
          center
        >
          <InputTypeIn
            placeholder="John Doe"
            value={fromName}
            onChange={(event) => setFromName(event.target.value)}
          />
        </InputLayouts.Horizontal>

        <div className="flex flex-row items-center justify-between pt-2">
          <div className="text-xs text-text-03">
            {userMailSettings?.last_tested_at
              ? t("settings.accounts.emailLastTested", {
                  date: new Date(
                    userMailSettings.last_tested_at
                  ).toLocaleString(),
                })
              : userMailSettings?.password_configured
                ? t("settings.accounts.emailNotTestedYet")
                : null}
          </div>
          <div className="flex flex-row gap-2">
            {userMailSettings?.is_active && (
              <Button
                danger
                secondary
                leftIcon={SvgTrash}
                disabled={isSaving || isTesting}
                onClick={() => setShowDeleteModal(true)}
              >
                {t("settings.accounts.removeEmailConfigButton")}
              </Button>
            )}
            <Button
              secondary
              leftIcon={SvgShare}
              disabled={
                isSaving ||
                isTesting ||
                areUserSettingsLoading ||
                !mailConfigId ||
                (!userMailSettings?.password_configured &&
                  !emailPassword.trim())
              }
              onClick={testSettings}
            >
              {isTesting
                ? t("settings.accounts.testingEmailButton")
                : t("settings.accounts.testEmailButton")}
            </Button>
            <Button
              leftIcon={SvgCheck}
              disabled={
                isSaving ||
                isTesting ||
                areUserSettingsLoading ||
                !emailUsername.trim() ||
                !fromEmail.trim() ||
                !mailConfigId
              }
              onClick={saveSettings}
            >
              {isSaving
                ? t("settings.accounts.savingEmailButton")
                : t("settings.accounts.saveEmailButton")}
            </Button>
          </div>
        </div>
      </Card>
      {showDeleteModal && (
        <ConfirmEntityModal
          danger
          entityType={t("settings.accounts.emailConfigEntity")}
          entityName={fromEmail}
          onClose={() => setShowDeleteModal(false)}
          onSubmit={deleteSettings}
        />
      )}
    </Section>
  );
}
