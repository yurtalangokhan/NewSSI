import { SlackChannelConfigCreationForm } from "../SlackChannelConfigCreationForm";
import { fetchSS } from "@/lib/utilsSS";
import { ErrorCallout } from "@/components/ErrorCallout";
import { DocumentSetSummary, SlackChannelConfig } from "@/lib/types";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { SvgSlack } from "@opal/icons";
import { FetchAgentsResponse, fetchAgentsSS } from "@/lib/agentsSS";
import { getStandardAnswerCategoriesIfEE } from "@/components/standardAnswers/getStandardAnswerCategoriesIfEE";
import i18n from "@/i18n/config";

async function EditslackChannelConfigPage(props: {
  params: Promise<{ id: number }>;
}) {
  const params = await props.params;
  const tasks = [
    fetchSS("/manage/admin/slack-app/channel"),
    fetchSS("/manage/document-set"),
    fetchAgentsSS(),
  ];

  const [
    slackChannelsResponse,
    documentSetsResponse,
    [assistants, agentsFetchError],
  ] = (await Promise.all(tasks)) as [Response, Response, FetchAgentsResponse];

  const eeStandardAnswerCategoryResponse =
    await getStandardAnswerCategoriesIfEE();

  if (!slackChannelsResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={i18n.t("admin.bots.somethingWentWrong")}
        errorMsg={`${i18n.t("admin.bots.failedToFetchSlackChannels")} - ${await slackChannelsResponse.text()}`}
      />
    );
  }
  const allslackChannelConfigs =
    (await slackChannelsResponse.json()) as SlackChannelConfig[];

  const slackChannelConfig = allslackChannelConfigs.find(
    (config) => config.id === Number(params.id)
  );

  if (!slackChannelConfig) {
    return (
      <ErrorCallout
        errorTitle={i18n.t("admin.bots.somethingWentWrong")}
        errorMsg={`${i18n.t("admin.bots.slackChannelConfigNotFound")} ID: ${params.id}`}
      />
    );
  }

  if (!documentSetsResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={i18n.t("admin.bots.somethingWentWrong")}
        errorMsg={`${i18n.t("admin.bots.failedToFetchDocumentSets")} - ${await documentSetsResponse.text()}`}
      />
    );
  }
  const response = await documentSetsResponse.json();
  const documentSets = response as DocumentSetSummary[];

  if (agentsFetchError) {
    return (
      <ErrorCallout
        errorTitle={i18n.t("admin.bots.somethingWentWrong")}
        errorMsg={`${i18n.t("admin.bots.failedToFetchPersonas")} - ${agentsFetchError}`}
      />
    );
  }

  return (
    <SettingsLayouts.Root>
      <InstantSSRAutoRefresh />
      <SettingsLayouts.Header
        icon={SvgSlack}
        title={
          slackChannelConfig.is_default
            ? "Edit Default Slack Config"
            : "Edit Slack Channel Config"
        }
        separator
        backButton
      />
      <SettingsLayouts.Body>
        <SlackChannelConfigCreationForm
          slack_bot_id={slackChannelConfig.slack_bot_id}
          documentSets={documentSets}
          personas={assistants}
          standardAnswerCategoryResponse={eeStandardAnswerCategoryResponse}
          existingSlackChannelConfig={slackChannelConfig}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

export default EditslackChannelConfigPage;
