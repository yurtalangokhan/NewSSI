import en from "@/i18n/locales/en";

export type GreetingKey = keyof typeof en.app.greetings;

export const GREETING_KEYS = Object.keys(en.app.greetings) as GreetingKey[];

export const GREETING_MESSAGES = Object.values(
  en.app.greetings
) as readonly string[];

export function getRandomGreeting(): string {
  return GREETING_MESSAGES[
    Math.floor(Math.random() * GREETING_MESSAGES.length)
  ] as string;
}
