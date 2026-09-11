"use client";

import { ErrorCallout } from "@/components/ErrorCallout";
import TableSkeleton from "@/refresh-components/skeletons/TableSkeleton";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import { SlackBotTable } from "./SlackBotTable";
import { useSlackBots } from "./[bot-id]/hooks";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import { DOCS_ADMINS_PATH } from "@/lib/constants";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import Text from "@/refresh-components/texts/Text";

function Main() {
  const { t } = useTranslation();
  const {
    data: slackBots,
    isLoading: isSlackBotsLoading,
    error: slackBotsError,
  } = useSlackBots();

  if (isSlackBotsLoading) {
    return (
      <TableSkeleton
        rowCount={3}
        columns={[
          { type: "icon-text", width: "w-48", headerWidth: "w-24" },
          { type: "text", width: "w-32", headerWidth: "w-20" },
          { type: "badge", width: "w-20", headerWidth: "w-16" },
          { type: "actions", width: "w-16", headerWidth: "w-16" },
        ]}
      />
    );
  }

  if (slackBotsError || !slackBots) {
    const errorMsg =
      slackBotsError?.info?.message ||
      slackBotsError?.info?.detail ||
      t("admin.bots.unknownError");

    return (
      <ErrorCallout
        errorTitle={t("admin.bots.errorLoadingApps")}
        errorMsg={`${errorMsg}`}
      />
    );
  }

  return (
    <div className="mb-8">
      <Text as="p" className="mb-2 text-sm text-muted-foreground">
        {t("admin.bots.description")}
      </Text>

      <div className="mb-2">
        <ul className="list-disc mt-2 ml-4 text-sm text-muted-foreground">
          <li>{t("admin.bots.featureAutoAnswer")}</li>
          <li>{t("admin.bots.featureDocSets")}</li>
          <li>{t("admin.bots.featureDirectMessage")}</li>
        </ul>
      </div>

      <Text as="p" className="mb-6 text-sm text-muted-foreground">
        {t("admin.bots.guidePrefix")}{" "}
        <a
          className="text-blue-500 hover:underline"
          href={`${DOCS_ADMINS_PATH}/getting_started/slack_bot_setup`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("admin.bots.guideLink")}{" "}
        </a>
        {t("admin.bots.guideSuffix")}
      </Text>

      <CreateButton href="/admin/bots/new">
        {t("admin.bots.newSlackBotButton")}
      </CreateButton>

      <SlackBotTable slackBots={slackBots} />
    </div>
  );
}

export default function Page() {
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SLACK_BOTS]!;
  const { t } = useTranslation();
  const { data: slackBots, isLoading: isSlackBotsLoading } = useSlackBots();
  const totalBots = slackBots?.length ?? 0;
  const activeBots = slackBots?.filter((b) => b.enabled).length ?? 0;
  const configuredChannels =
    slackBots?.reduce((sum, b) => sum + b.configs_count, 0) ?? 0;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          isLoading={isSlackBotsLoading}
          title={t("admin.bots.workspaceTitle", {
            defaultValue: "Slack bot workspace",
          })}
          description={t("admin.bots.workspaceDescription", {
            defaultValue:
              "Manage Slack bot connections, channel routing, and chat entry points for workspace users.",
          })}
          metrics={[
            {
              label: t("admin.bots.totalBotsLabel", {
                defaultValue: "Total bots",
              }),
              value: isSlackBotsLoading ? "..." : String(totalBots),
            },
            {
              label: t("admin.bots.activeBotsLabel", {
                defaultValue: "Active bots",
              }),
              value: isSlackBotsLoading ? "..." : String(activeBots),
              tone:
                !isSlackBotsLoading && totalBots > 0 && activeBots === totalBots
                  ? "success"
                  : !isSlackBotsLoading && activeBots < totalBots
                    ? "warning"
                    : "neutral",
            },
            {
              label: t("admin.bots.configuredChannelsLabel", {
                defaultValue: "Configured channels",
              }),
              value: isSlackBotsLoading ? "..." : String(configuredChannels),
            },
          ]}
        />
        <InstantSSRAutoRefresh />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
