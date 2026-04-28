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
      <ErrorCallout errorTitle={t("admin.bots.errorLoadingApps")} errorMsg={`${errorMsg}`} />
    );
  }

  return (
    <div className="mb-8">
      <p className="mb-2 text-sm text-muted-foreground">
        {t("admin.bots.description")}
      </p>

      <div className="mb-2">
        <ul className="list-disc mt-2 ml-4 text-sm text-muted-foreground">
          <li>{t("admin.bots.featureAutoAnswer")}</li>
          <li>{t("admin.bots.featureDocSets")}</li>
          <li>{t("admin.bots.featureDirectMessage")}</li>
        </ul>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">
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
      </p>

      <CreateButton href="/admin/bots/new">{t("admin.bots.newSlackBotButton")}</CreateButton>

      <SlackBotTable slackBots={slackBots} />
    </div>
  );
}

export default function Page() {
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SLACK_BOTS]!;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header icon={route.icon} title={route.title} separator />
      <SettingsLayouts.Body>
        <InstantSSRAutoRefresh />
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
