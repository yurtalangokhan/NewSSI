import { SlackChannelConfigCreationForm } from "../SlackChannelConfigCreationForm";
import { fetchSS } from "@/lib/utilsSS";
import { ErrorCallout } from "@/components/ErrorCallout";
import { DocumentSetSummary, SlackChannelConfig } from "@/lib/types";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { SvgSlack } from "@opal/icons";
import { FetchAgentsResponse, fetchAgentsSS } from "@/lib/agentsSS";
import { getStandardAnswerCategoriesIfEE } from "@/components/standardAnswers/getStandardAnswerCategoriesIfEE";
import { tServer } from "@/i18n/server";
import { resolveLocaleSS } from "@/lib/localeSS";

async function EditslackChannelConfigPage(props: {
  params: Promise<{ id: number }>;
}) {
  const params = await props.params;
  const [
    slackChannelsResponse,
    documentSetsResponse,
    [assistants, agentsFetchError],
    locale,
  ] = await Promise.all([
    fetchSS("/manage/admin/slack-app/channel") as Promise<Response>,
    fetchSS("/manage/document-set") as Promise<Response>,
    fetchAgentsSS() as Promise<FetchAgentsResponse>,
    resolveLocaleSS(),
  ]);

  const eeStandardAnswerCategoryResponse =
    await getStandardAnswerCategoriesIfEE();

  if (!slackChannelsResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.bots.somethingWentWrong", { lng: locale })}
        errorMsg={`${tServer("admin.bots.failedToFetchSlackChannels", {
          lng: locale,
        })} - ${await slackChannelsResponse.text()}`}
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
        errorTitle={tServer("admin.bots.somethingWentWrong", { lng: locale })}
        errorMsg={`${tServer("admin.bots.slackChannelConfigNotFound", {
          lng: locale,
        })} ID: ${params.id}`}
      />
    );
  }

  if (!documentSetsResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.bots.somethingWentWrong", { lng: locale })}
        errorMsg={`${tServer("admin.bots.failedToFetchDocumentSets", {
          lng: locale,
        })} - ${await documentSetsResponse.text()}`}
      />
    );
  }
  const response = await documentSetsResponse.json();
  const documentSets = response as DocumentSetSummary[];

  if (agentsFetchError) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.bots.somethingWentWrong", { lng: locale })}
        errorMsg={`${tServer("admin.bots.failedToFetchPersonas", {
          lng: locale,
        })} - ${agentsFetchError}`}
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
