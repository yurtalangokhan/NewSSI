"use client";

import { useState } from "react";
import CardGridSkeleton from "@/refresh-components/skeletons/CardGridSkeleton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { toast } from "@/hooks/useToast";
import { Section } from "@/layouts/general-layouts";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import Modal from "@/refresh-components/Modal";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import Card from "@/refresh-components/cards/Card";
import { SvgKey } from "@opal/icons";
import {
  useDiscordGuilds,
  useDiscordBotConfig,
} from "@/app/admin/discord-bot/hooks";
import { createGuildConfig } from "@/app/admin/discord-bot/lib";
import { DiscordGuildsTable } from "@/app/admin/discord-bot/DiscordGuildsTable";
import { BotConfigCard } from "@/app/admin/discord-bot/BotConfigCard";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

function DiscordBotContent() {
  const { data: guilds, isLoading, error, refreshGuilds } = useDiscordGuilds();
  const { t } = useTranslation();
  const { data: botConfig, isManaged } = useDiscordBotConfig();
  const [registrationKey, setRegistrationKey] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Bot is available if:
  // - Managed externally (Cloud/env) - assume it's configured
  // - Self-hosted and explicitly configured via UI
  const isBotAvailable = isManaged || botConfig?.configured === true;

  const handleCreateGuild = async () => {
    setIsCreating(true);
    try {
      const result = await createGuildConfig();
      setRegistrationKey(result.registration_key);
      refreshGuilds();
      toast.success(t("admin.discord.serverConfigCreated"));
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("admin.discord.createServerFailed")
      );
    } finally {
      setIsCreating(false);
    }
  };

  if (isLoading) {
    return <CardGridSkeleton cardCount={2} columnsClassName="grid-cols-1" />;
  }

  if (error || !guilds) {
    return (
      <ErrorCallout
        errorTitle={t("admin.discord.loadServersErrorTitle")}
        errorMsg={error?.info?.detail || t("admin.discord.unknownError")}
      />
    );
  }

  return (
    <>
      <BotConfigCard />

      <Modal open={!!registrationKey}>
        <Modal.Content width="sm">
          <Modal.Header
            title={t("admin.discord.registrationKeyTitle")}
            icon={SvgKey}
            onClose={() => setRegistrationKey(null)}
            description={t("admin.discord.registrationKeyDescription")}
          />
          <Modal.Body>
            <Text text04 mainUiBody>
              {t("admin.discord.registrationKeyInstructions")}
            </Text>
            <Card variant="secondary">
              <Section
                flexDirection="row"
                justifyContent="between"
                alignItems="center"
              >
                <Text text03 secondaryMono>
                  !register {registrationKey}
                </Text>
                <CopyIconButton
                  getCopyText={() => `!register ${registrationKey}`}
                />
              </Section>
            </Card>
          </Modal.Body>
        </Modal.Content>
      </Modal>

      <Card variant={!isBotAvailable ? "disabled" : "primary"}>
        <Section
          flexDirection="row"
          justifyContent="between"
          alignItems="center"
        >
          <Text mainContentEmphasis text05>
            {t("admin.discord.serverConfigurations")}
          </Text>
          <CreateButton
            onClick={handleCreateGuild}
            disabled={isCreating || !isBotAvailable}
          >
            {isCreating ? "Creating..." : "Add Server"}
          </CreateButton>
        </Section>
        <DiscordGuildsTable guilds={guilds} onRefresh={refreshGuilds} />
      </Card>
    </>
  );
}

export default function Page() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DISCORD_BOTS]!;
  const { data: guilds, isLoading: isGuildsLoading } = useDiscordGuilds();
  const { data: botConfig, isManaged } = useDiscordBotConfig();
  const isBotAvailable = isManaged || botConfig?.configured === true;
  const totalServers = guilds?.length ?? 0;
  const registeredServers =
    guilds?.filter((g) => g.guild_id != null).length ?? 0;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={t("admin.discord.pageDescription")}
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.discord.workspaceTitle", {
            defaultValue: "Discord bot workspace",
          })}
          description={t("admin.discord.workspaceDescription", {
            defaultValue:
              "Register Discord servers, manage bot tokens, and route channels to the right default agent.",
          })}
          metrics={[
            {
              label: t("admin.discord.totalServersLabel", {
                defaultValue: "Total servers",
              }),
              value: isGuildsLoading ? "..." : String(totalServers),
            },
            {
              label: t("admin.discord.registeredServersLabel", {
                defaultValue: "Registered servers",
              }),
              value: isGuildsLoading ? "..." : String(registeredServers),
            },
            {
              label: t("admin.discord.botStatusLabel", {
                defaultValue: "Bot status",
              }),
              value: isBotAvailable
                ? t("admin.discord.botAvailable", { defaultValue: "Available" })
                : t("admin.discord.botUnavailable", {
                    defaultValue: "Not configured",
                  }),
              tone: isBotAvailable ? "success" : "warning",
            },
          ]}
        />
        <DiscordBotContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
