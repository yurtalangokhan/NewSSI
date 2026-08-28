"use client";

import { ErrorCallout } from "@/components/ErrorCallout";
import { ThreeDotsLoader } from "@/components/Loading";
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
    return <ThreeDotsLoader />;
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

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={
          route.titleKey
            ? t(route.titleKey, { defaultValue: route.title })
            : route.title
        }
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.bots.workspaceTitle", {
            defaultValue: "Slack bot workspace",
          })}
          description={t("admin.bots.workspaceDescription", {
            defaultValue:
              "Manage Slack bot connections, channel routing, and chat entry points for workspace users.",
          })}
          metrics={[
            {
              label: t("admin.bots.integrationLabel", {
                defaultValue: "Integration",
              }),
              value: "Slack",
            },
            {
              label: t("admin.bots.routingLabel", {
                defaultValue: "Routing",
              }),
              value: t("admin.bots.channels", {
                defaultValue: "Channels",
              }),
            },
            {
              label: t("admin.bots.agentLayerLabel", {
                defaultValue: "Agent layer",
              }),
              value: t("admin.navigation.routes.agents.sidebar", {
                defaultValue: "Agents",
              }),
            },
          ]}
          actions={[
            {
              label: t("admin.bots.newSlackBotButton"),
              href: "/admin/bots/new",
              primary: true,
            },
            {
              label: t("admin.navigation.routes.agents.sidebar", {
                defaultValue: "Agents",
              }),
              href: ADMIN_PATHS.AGENTS,
            },
          ]}
        />
        <InstantSSRAutoRefresh />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
