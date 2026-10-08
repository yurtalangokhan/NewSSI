import { SlackChannelConfigCreationForm } from "../SlackChannelConfigCreationForm";
import { fetchSlackChannelsSS } from "@/lib/api/domains/integrations/server";
import { fetchDocumentSetsSS } from "@/lib/api/domains/knowledge/server";
import { ErrorCallout } from "@/components/ErrorCallout";
import { DocumentSetSummary, SlackChannelConfig } from "@/lib/types";
import { InstantSSRAutoRefresh } from "@/components/SSRAutoRefresh";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { SvgSlack } from "@opal/icons";
import {
  type FetchAgentsResponse,
  fetchAgentsSS,
} from "@/lib/api/domains/agents/server";
import { getStandardAnswerCategoriesIfEE } from "@/components/standardAnswers/getStandardAnswerCategoriesIfEE";
import { tServer } from "@/i18n/server";
import { resolveLocaleSS } from "@/lib/i18n/locale.server";
import { requireAdminAuth } from "@/lib/auth/requireAuth";
import { ADMIN_PATHS } from "@/lib/navigation/admin-routes";
import { redirect } from "next/navigation";
import type { Route } from "next";

async function EditslackChannelConfigPage(props: {
  params: Promise<{ id: number }>;
}) {
  const auth = await requireAdminAuth(ADMIN_PATHS.SLACK_BOTS);
  if (auth.redirect) redirect(auth.redirect as Route);

  const params = await props.params;
  const [
    slackChannelsResponse,
    documentSetsResponse,
    [assistants, agentsFetchError],
    locale,
  ] = await Promise.all([
    fetchSlackChannelsSS(),
    fetchDocumentSetsSS(),
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
