import { Persona } from "@/lib/api/domains/agents/types";

export function isPersonaASlackBotPersona(persona: Persona) {
  return persona.name.startsWith("__slack_bot_persona__");
}
