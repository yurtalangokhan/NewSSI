"use client";

import { use } from "react";
import BackButton from "@/refresh-components/buttons/BackButton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { useTranslation } from "react-i18next";
import { ThreeDotsLoader } from "@/components/Loading";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import SlackChannelConfigsTable from "./SlackChannelConfigsTable";
import { useSlackBot, useSlackChannelConfigsByBot } from "./hooks";
import { ExistingSlackBotForm } from "../SlackBotUpdateForm";
import Separator from "@/refresh-components/Separator";

function SlackBotEditPage({
  params,
}: {
  params: Promise<{ "bot-id": string }>;
}) {
  const { t } = useTranslation();
  const unwrappedParams = use(params);

  const {
    data: slackBot,
    isLoading: isSlackBotLoading,
    error: slackBotError,
    refreshSlackBot,
  } = useSlackBot(Number(unwrappedParams["bot-id"]));

  const {
    data: slackChannelConfigs,
    isLoading: isSlackChannelConfigsLoading,
    error: slackChannelConfigsError,
    refreshSlackChannelConfigs,
  } = useSlackChannelConfigsByBot(Number(unwrappedParams["bot-id"]));

  if (isSlackBotLoading || isSlackChannelConfigsLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <ThreeDotsLoader />
      </div>
    );
  }

  if (slackBotError || !slackBot) {
    const errorMsg =
      slackBotError?.info?.message ||
      slackBotError?.info?.detail ||
      t("admin.bots.unknownError");
    return (
      <ErrorCallout
        errorTitle={t("admin.bots.somethingWentWrong")}
        errorMsg={t("admin.bots.failedToFetchBot", { id: unwrappedParams["bot-id"], errorMsg })}
      />
    );
  }

  if (slackChannelConfigsError || !slackChannelConfigs) {
    const errorMsg =
      slackChannelConfigsError?.info?.message ||
      slackChannelConfigsError?.info?.detail ||
      t("admin.bots.unknownError");
    return (
      <ErrorCallout
        errorTitle={t("admin.bots.somethingWentWrong")}
        errorMsg={t("admin.bots.failedToFetchBot", { id: unwrappedParams["bot-id"], errorMsg })}
      />
    );
  }

  return (
    <>
      <InstantSSRAutoRefresh />

      <BackButton routerOverride="/admin/bots" />

      <ExistingSlackBotForm
        existingSlackBot={slackBot}
        refreshSlackBot={refreshSlackBot}
      />
      <Separator />

      <div className="mt-8">
        <SlackChannelConfigsTable
          slackBotId={slackBot.id}
          slackChannelConfigs={slackChannelConfigs}
          refresh={refreshSlackChannelConfigs}
        />
      </div>
    </>
  );
}

export default function Page({
  params,
}: {
  params: Promise<{ "bot-id": string }>;
}) {
  return (
    <>
      <SlackBotEditPage params={params} />
    </>
  );
}
