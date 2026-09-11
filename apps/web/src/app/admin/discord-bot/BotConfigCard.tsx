"use client";

import { useState } from "react";
import { Section } from "@/layouts/general-layouts";
import Text from "@/refresh-components/texts/Text";
import Card from "@/refresh-components/cards/Card";
import Button from "@/refresh-components/buttons/Button";
import { Badge } from "@/components/ui/badge";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import FormSkeleton from "@/refresh-components/skeletons/FormSkeleton";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import {
  useDiscordBotConfig,
  useDiscordGuilds,
} from "@/app/admin/discord-bot/hooks";
import { createBotConfig, deleteBotConfig } from "@/app/admin/discord-bot/lib";
import { toast } from "@/hooks/useToast";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { getFormattedDateTime } from "@/lib/dateUtils";
import { useTranslation } from "react-i18next";

export function BotConfigCard() {
  const { t } = useTranslation();
  const {
    data: botConfig,
    isLoading,
    isManaged,
    refreshBotConfig,
  } = useDiscordBotConfig();
  const { data: guilds } = useDiscordGuilds();

  const [botToken, setBotToken] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Don't render anything if managed externally (Cloud or env var)
  if (isManaged) {
    return null;
  }

  // Show loading while fetching initial state
  if (isLoading) {
    return (
      <Card>
        <Section
          flexDirection="row"
          justifyContent="between"
          alignItems="center"
        >
          <Text mainContentEmphasis text05>
            {t("admin.discord.botTokenTitle")}
          </Text>
        </Section>
        <div className="py-3">
          <FormSkeleton fieldCount={2} hasSubmitButton={false} />
        </div>
      </Card>
    );
  }

  const isConfigured = botConfig?.configured ?? false;
  const hasServerConfigs = (guilds?.length ?? 0) > 0;

  const handleSaveToken = async () => {
    if (!botToken.trim()) {
      toast.error(t("admin.discord.enterBotToken"));
      return;
    }

    setIsSubmitting(true);
    try {
      await createBotConfig(botToken.trim());
      setBotToken("");
      refreshBotConfig();
      toast.success(t("admin.discord.botTokenSaved"));
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("admin.discord.botTokenSaveFailed")
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteToken = async () => {
    setIsSubmitting(true);
    try {
      await deleteBotConfig();
      refreshBotConfig();
      toast.success(t("admin.discord.botTokenDeleted"));
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("admin.discord.botTokenDeleteFailed")
      );
    } finally {
      setIsSubmitting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <>
      {showDeleteConfirm && (
        <ConfirmEntityModal
          danger
          entityType={t("admin.discord.botTokenEntityType")}
          entityName={t("admin.discord.botTokenEntityName")}
          onClose={() => setShowDeleteConfirm(false)}
          onSubmit={handleDeleteToken}
          additionalDetails={t("admin.discord.botTokenDeleteDetails")}
        />
      )}
      <Card>
        <Section flexDirection="row" justifyContent="between">
          <Section flexDirection="row" gap={0.5} width="fit">
            <Text mainContentEmphasis text05>
              {t("admin.discord.botTokenTitle")}
            </Text>
            {isConfigured ? (
              <Badge variant="success">
                {t("admin.discord.botConfigured")}
              </Badge>
            ) : (
              <Badge variant="secondary">
                {t("admin.discord.botNotConfigured")}
              </Badge>
            )}
          </Section>
          {isConfigured && (
            <SimpleTooltip
              tooltip={
                hasServerConfigs
                  ? t("admin.discord.deleteServerConfigsFirst")
                  : undefined
              }
              disabled={!hasServerConfigs}
            >
              <Button
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isSubmitting || hasServerConfigs}
                danger
              >
                {t("admin.discord.deleteDiscordToken")}
              </Button>
            </SimpleTooltip>
          )}
        </Section>

        {isConfigured ? (
          <Section flexDirection="column" alignItems="start" gap={0.5}>
            <Text text03 secondaryBody>
              {t("admin.discord.botConfiguredMessage")}
              {botConfig?.created_at && (
                <>
                  {" "}
                  {t("admin.discord.botConfiguredAt", {
                    date: getFormattedDateTime(new Date(botConfig.created_at)),
                  })}
                </>
              )}
            </Text>
            <Text text03 secondaryBody>
              {t("admin.discord.changeTokenHint")}
            </Text>
          </Section>
        ) : (
          <Section flexDirection="column" alignItems="start" gap={0.75}>
            <Text text03 secondaryBody>
              {t("admin.discord.enterTokenDescription")}
            </Text>
            <Section flexDirection="row" alignItems="end" gap={0.5}>
              <PasswordInputTypeIn
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder={t("admin.discord.botTokenPlaceholder")}
                disabled={isSubmitting}
                className="flex-1"
              />
              <Button
                onClick={handleSaveToken}
                disabled={isSubmitting || !botToken.trim()}
              >
                {isSubmitting
                  ? t("admin.discord.saving")
                  : t("admin.discord.saveToken")}
              </Button>
            </Section>
          </Section>
        )}
      </Card>
    </>
  );
}
