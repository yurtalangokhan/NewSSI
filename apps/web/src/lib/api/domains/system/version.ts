import { appSettings } from "@/lib/settings";

export const getWebVersion = (): string | null => {
  return appSettings.ATLAS_VERSION;
};
