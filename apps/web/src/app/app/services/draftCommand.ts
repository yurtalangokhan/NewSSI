export interface AppDraftCommand {
  agentId?: string;
  message: string;
  submitOnLoad: boolean;
}

const APP_DRAFT_COMMAND_KEY = "onyx:app:draft-command";

function getSessionStorage() {
  if (typeof sessionStorage === "undefined") {
    return null;
  }
  return sessionStorage;
}

export function saveAppDraftCommand(command: AppDraftCommand) {
  getSessionStorage()?.setItem(APP_DRAFT_COMMAND_KEY, JSON.stringify(command));
}

export function consumeAppDraftCommand({
  agentId,
}: {
  agentId?: string | null;
} = {}) {
  const storage = getSessionStorage();
  const rawCommand = storage?.getItem(APP_DRAFT_COMMAND_KEY);
  if (!storage || !rawCommand) {
    return null;
  }

  let command: AppDraftCommand;
  try {
    command = JSON.parse(rawCommand) as AppDraftCommand;
  } catch {
    storage.removeItem(APP_DRAFT_COMMAND_KEY);
    return null;
  }

  if (
    command.agentId &&
    agentId &&
    String(command.agentId) !== String(agentId)
  ) {
    return null;
  }

  storage.removeItem(APP_DRAFT_COMMAND_KEY);
  return command;
}
