import { SlackChannelConfigCreationForm } from "../SlackChannelConfigCreationForm";
import { tServer } from "@/i18n/server";
import { fetchDocumentSetsSS } from "@/lib/api/domains/knowledge/server";
import { ErrorCallout } from "@/components/ErrorCallout";
import { DocumentSetSummary } from "@/lib/types";
import { fetchAgentsSS } from "@/lib/api/domains/agents/server";
import { getStandardAnswerCategoriesIfEE } from "@/components/standardAnswers/getStandardAnswerCategoriesIfEE";
import { redirect } from "next/navigation";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { SvgSlack } from "@opal/icons";
import { resolveLocaleSS } from "@/lib/i18n/locale.server";
import { requireAdminAuth } from "@/lib/auth/requireAuth";
import { ADMIN_PATHS } from "@/lib/navigation/admin-routes";
import type { Route } from "next";

async function NewChannelConfigPage(props: {
  params: Promise<{ "bot-id": string }>;
}) {
  const auth = await requireAdminAuth(ADMIN_PATHS.SLACK_BOTS);
  if (auth.redirect) redirect(auth.redirect as Route);

  const unwrappedParams = await props.params;
  const slack_bot_id_raw = unwrappedParams?.["bot-id"] || null;
  const slack_bot_id = slack_bot_id_raw
    ? parseInt(slack_bot_id_raw as string, 10)
    : null;
  if (!slack_bot_id || isNaN(slack_bot_id)) {
    redirect("/admin/bots");
    return null;
  }

  const [
    documentSetsResponse,
    agentsResponse,
    standardAnswerCategoryResponse,
    locale,
  ] = await Promise.all([
    fetchDocumentSetsSS(),
    fetchAgentsSS(),
    getStandardAnswerCategoriesIfEE(),
    resolveLocaleSS(),
  ]);

  if (!documentSetsResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch document sets - ${await documentSetsResponse.text()}`}
      />
    );
  }
  const documentSets =
    (await documentSetsResponse.json()) as DocumentSetSummary[];

  if (agentsResponse[1]) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch agents - ${agentsResponse[1]}`}
      />
    );
  }

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgSlack}
        title={tServer("admin.newChannelConfigPage.title", { lng: locale })}
        separator
        backButton
      />
      <SettingsLayouts.Body>
        <SlackChannelConfigCreationForm
          slack_bot_id={slack_bot_id}
          documentSets={documentSets}
          personas={agentsResponse[0]}
          standardAnswerCategoryResponse={standardAnswerCategoryResponse}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

export default NewChannelConfigPage;
