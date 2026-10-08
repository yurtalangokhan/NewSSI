export enum AuthType {
  BASIC = "basic",
  GOOGLE_OAUTH = "google_oauth",
  OIDC = "oidc",
  SAML = "saml",
  CLOUD = "cloud",
}

// Nothing environment-backed lives here. Every setting read from the
// environment — service URLs, auth mode, branding, feature flags — is declared
// in lib/env/schema.ts and consumed through lib/settings.ts. This module holds
// only fixed constants.

// Documentation URLs
export const DOCS_BASE_URL = "https://docs.atlas.app";
export const DOCS_ADMINS_PATH = `${DOCS_BASE_URL}/admins`;

export const TENANT_ID_COOKIE_NAME = "atlas_tid";

export const GMAIL_AUTH_IS_ADMIN_COOKIE_NAME = "gmail_auth_is_admin";

export const GOOGLE_DRIVE_AUTH_IS_ADMIN_COOKIE_NAME =
  "google_drive_auth_is_admin";

export const SEARCH_TYPE_COOKIE_NAME = "search_type";
export const AGENTIC_SEARCH_TYPE_COOKIE_NAME = "agentic_type";

export const TOGGLED_CONNECTORS_COOKIE_NAME = "toggled_connectors";

// Restrict markdown links to safe protocols
export const ALLOWED_URL_PROTOCOLS = ["http:", "https:", "mailto:"] as const;

// Agent/Persona related constants
export const MAX_CHARACTERS_PERSONA_DESCRIPTION = 5000000;
export const MAX_CHARACTERS_AGENT_DESCRIPTION = 500;
export const MAX_STARTER_MESSAGES = 4;
export const MAX_CHARACTERS_STARTER_MESSAGE = 200;
export const STARTER_MESSAGES_EXAMPLES = [
  "Give me an overview of some documents.",
  "Find the latest sales report.",
  "Compile a list of our engineering goals for this quarter.",
  "Summarize my goals for today.",
];

//Credential form data key constants
export const CREDENTIAL_NAME = "name";
export const CREDENTIAL_SOURCE = "source";
export const CREDENTIAL_UPLOADED_FILE = "uploaded_file";
export const CREDENTIAL_FIELD_KEY = "field_key";
export const CREDENTIAL_TYPE_DEFINITION_KEY = "type_definition_key";
export const CREDENTIAL_JSON = "credential_json";

export const MODAL_ROOT_ID = "modal-root";

export const ANONYMOUS_USER_NAME = "Anonymous";
export const UNNAMED_CHAT = "New Chat";

export const DEFAULT_AGENT_ID = 0;
export const GENERAL_ASSISTANT_ID = -1;
export const IMAGE_ASSISTANT_ID = -2;
export const ART_ASSISTANT_ID = -3;

// Used in the File Picker to show a max number of files.
// The rest will be hidden behind an "All Recent Files" button.
export const MAX_FILES_TO_SHOW = 3;

// SIZES
export const MOBILE_SIDEBAR_BREAKPOINT_PX = 640;
export const DEFAULT_AGENT_AVATAR_SIZE_PX = 18;
export const HORIZON_DISTANCE_PX = 800;
export const LOGO_FOLDED_SIZE_PX = 24;
export const LOGO_UNFOLDED_SIZE_PX = 88;

export const DEFAULT_CONTEXT_TOKENS = 120_000;
export const MAX_CHUNKS_FED_TO_CHAT = 25;
