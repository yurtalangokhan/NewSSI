import { StandardAnswerCreationForm } from "@/app/ee/admin/standard-answer/StandardAnswerCreationForm";
import { tServer } from "@/i18n/server";
import { fetchStandardAnswerCategoriesSS } from "@/lib/api/domains/knowledge/server";
import { ErrorCallout } from "@/components/ErrorCallout";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/navigation/admin-routes";
import { StandardAnswerCategory } from "@/lib/types";
import { resolveLocaleSS } from "@/lib/i18n/locale.server";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.STANDARD_ANSWERS]!;

async function Page() {
  const [standardAnswerCategoriesResponse, locale] = await Promise.all([
    fetchStandardAnswerCategoriesSS(),
    resolveLocaleSS(),
  ]);

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
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={tServer("admin.standardAnswerPages.newTitle", { lng: locale })}
        backButton
        separator
      />
      <SettingsLayouts.Body>
        <StandardAnswerCreationForm
          standardAnswerCategories={standardAnswerCategories}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

export default Page;
