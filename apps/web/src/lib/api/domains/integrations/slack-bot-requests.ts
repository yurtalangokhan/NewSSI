export interface SlackBotCreationRequest {
  name: string;
  enabled: boolean;

  bot_token: string;
  app_token: string;
  user_token?: string;
}

export const buildRequestBodyFromCreationRequest = (
  creationRequest: SlackBotCreationRequest
): string => {
  return JSON.stringify({
    name: creationRequest.name,
    enabled: creationRequest.enabled,
    bot_token: creationRequest.bot_token,
    app_token: creationRequest.app_token,
    user_token: creationRequest.user_token,
  });
};
