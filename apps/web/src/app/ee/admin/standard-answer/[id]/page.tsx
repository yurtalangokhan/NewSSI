import { StandardAnswerCreationForm } from "@/app/ee/admin/standard-answer/StandardAnswerCreationForm";
import { tServer } from "@/i18n/server";
import { fetchSS } from "@/lib/utilsSS";
import { ErrorCallout } from "@/components/ErrorCallout";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { StandardAnswer, StandardAnswerCategory } from "@/lib/types";
import { resolveLocaleSS } from "@/lib/localeSS";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.STANDARD_ANSWERS]!;

async function Main({ id }: { id: string }) {
  const [standardAnswersResponse, standardAnswerCategoriesResponse, locale] =
    await Promise.all([
      fetchSS("/manage/admin/standard-answer"),
      fetchSS(`/manage/admin/standard-answer/category`),
      resolveLocaleSS(),
    ]);

  if (standardAnswersResponse === undefined) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch standard answers.`}
      />
    );
  }

  if (!standardAnswersResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch standard answers - ${await standardAnswersResponse.text()}`}
      />
    );
  }
  const allStandardAnswers =
    (await standardAnswersResponse.json()) as StandardAnswer[];
  const standardAnswer = allStandardAnswers.find(
    (answer) => answer.id.toString() === id
  );

  if (!standardAnswer) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Did not find standard answer with ID: ${id}`}
      />
    );
  }

  if (standardAnswerCategoriesResponse === undefined) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch standard answer categories.`}
      />
    );
  }

  if (!standardAnswerCategoriesResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={tServer("admin.standardAnswerCategories.fetchError", {
          lng: locale,
        })}
        errorMsg={`Failed to fetch standard answer categories - ${await standardAnswerCategoriesResponse.text()}`}
      />
    );
  }

  const standardAnswerCategories =
    (await standardAnswerCategoriesResponse.json()) as StandardAnswerCategory[];

  return (
    <StandardAnswerCreationForm
      standardAnswerCategories={standardAnswerCategories}
      existingStandardAnswer={standardAnswer}
    />
  );
}

export default async function Page(props: { params: Promise<{ id: string }> }) {
  const [params, locale] = await Promise.all([
    props.params,
    resolveLocaleSS(),
  ]);

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={tServer("admin.standardAnswerPages.editTitle", { lng: locale })}
        backButton
        separator
      />
      <SettingsLayouts.Body>
        <Main id={params.id} />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
