import { StandardAnswerCreationForm } from "@/app/ee/admin/standard-answer/StandardAnswerCreationForm";
import i18n from "@/i18n/config";
import { fetchSS } from "@/lib/utilsSS";
import { ErrorCallout } from "@/components/ErrorCallout";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { StandardAnswerCategory } from "@/lib/types";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.STANDARD_ANSWERS]!;

async function Page() {
  const standardAnswerCategoriesResponse = await fetchSS(
    "/manage/admin/standard-answer/category"
  );

  if (!standardAnswerCategoriesResponse.ok) {
    return (
      <ErrorCallout
        errorTitle={i18n.t("admin.standardAnswerCategories.fetchError")}
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
        title={i18n.t("admin.standardAnswerPages.newTitle")}
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
