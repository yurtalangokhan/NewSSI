function requireEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Required environment variable ${name} is not set`);
  }
  return value;
}

export function getInternalUrl(): string {
  return requireEnv("INTERNAL_URL");
}

export function getAgentServiceUrl(): string {
  return requireEnv("AGENT_SERVICE_URL");
}

export function getRagServiceUrl(): string {
  return requireEnv("LANGCONNECT_URL");
}

export function getUserServiceUrl(): string {
  return requireEnv("USER_SERVICE_URL");
}

export function getToolsServiceUrl(): string {
  return requireEnv("TOOLS_SERVICE_URL");
}
