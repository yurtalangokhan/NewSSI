import { createSettingsPatchRoute } from "@/lib/api/userSettingsRoute";
import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";

export const PATCH = createSettingsPatchRoute(
  preferencesEndpoints.defaultModel
);
