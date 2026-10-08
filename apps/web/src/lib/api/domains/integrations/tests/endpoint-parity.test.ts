import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";

describe("integration endpoint parity", () => {
  it("preserves encoded integration identifiers", () => {
    expect(integrationsEndpoints.slackBotDetail(12).browserPath).toBe(
      "/api/manage/admin/slack-app/bots/12"
    );
    expect(integrationsEndpoints.slackChannelConfigByBot(12).browserPath).toBe(
      "/api/manage/admin/slack-app/bots/12/config"
    );
    expect(integrationsEndpoints.discordGuild(12).browserPath).toBe(
      `${integrationsEndpoints.discordGuildCatalog.browserPath}/12`
    );
    expect(integrationsEndpoints.discordChannels(12).browserPath).toBe(
      `${integrationsEndpoints.discordGuildCatalog.browserPath}/12/channels`
    );
    expect(integrationsEndpoints.gmailAuthorize(12).browserPath).toBe(
      "/api/manage/connector/gmail/authorize/12"
    );
    expect(integrationsEndpoints.googleDriveAuthorize(12).browserPath).toBe(
      "/api/manage/connector/google-drive/authorize/12"
    );
  });
});
